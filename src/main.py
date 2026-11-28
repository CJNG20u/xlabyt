import os
import psutil
import shutil
import subprocess
import sys
import time
from threading import Thread
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import dnscache  # noqa: F401  (caches DNS lookups process-wide; reads DNS_CACHE_TTL)
from external import External
from dotenv import load_dotenv

os.chdir(os.path.dirname(__file__))

print('Loading configuration from environment, env file and command line arguments')

load_dotenv()

for arg in sys.argv[1:]:
    if arg.startswith('-') and '=' in arg:
        key, value = arg.split('=', 1)
        os.environ[key.upper().lstrip('-').replace('-', '_')] = value

app_title = os.environ.get('APP_TITLE', 'xlab-yt')
theme_color = os.environ.get('THEME_COLOR', '#fa233b')
generate_sprite_below = int(os.environ.get('GENERATE_SPRITE_BELOW', '1800'))
max_video_age = int(os.environ.get('MAX_VIDEO_AGE', '3600'))
max_video_duration = int(os.environ.get('MAX_VIDEO_DURATION', '36000'))
default_quality = int(os.environ.get('DEFAULT_QUALITY', '720'))
max_quality = int(os.environ.get('MAX_QUALITY', '2160'))
codec_preference = [c.lower() for c in (os.environ.get('CODEC_PREFERENCE') or 'av01,vp9,opus').split(',') if c != '']
autoplay = (os.environ.get('AUTOPLAY', 'False')).lower() == 'true'
min_live_buffer = float(os.environ.get('MIN_LIVE_BUFFER', '1'))
always_transcode = (os.environ.get('ALWAYS_TRANSCODE', 'False')).lower() == 'true'
disable_transcoding = os.environ.get('DISABLE_TRANSCODING', 'False').lower() == 'true'
max_processes = int(os.environ.get('MAX_PROCESSES', '5'))
autoskip_sb_segments = [seg for seg in (os.environ.get('AUTOSKIP_SB_SEGMENTS') or '').split(',') if seg != '']
cookies_only_on_failure = (os.environ.get('COOKIES_ONLY_ON_FAILURE', 'True')).lower() == 'true'
amoled_bg = os.environ.get('AMOLED_BG', 'False').lower() == 'true'
playlist_support = os.environ.get('PLAYLIST_SUPPORT', 'True').lower() == 'true'
auto_bg_playback = os.environ.get('AUTO_BG_PLAYBACK', 'True').lower() == 'true'
audio_visualizer = os.environ.get('AUDIO_VISUALIZER', 'False').lower() == 'true'
data_path = os.path.abspath(os.environ.get('DATA_PATH', './data'))
proxies = [proxy for proxy in (os.environ.get('PROXIES') or 'local').split(',') if proxy != '']
impersonate_browser = os.environ.get('IMPERSONATE_BROWSER', 'chrome')
port = int(os.environ.get('PORT', '5000'))
publish_with_cloudflare = (os.environ.get('PUBLISH_WITH_CLOUDFLARE', 'False')).lower() == 'true'
linked_pid = int(os.environ.get('LINKED_PID', '0'))
# bgutil PO token provider (separate container), e.g. http://bgutil-provider:4416. Lets YouTube's
# mweb client stream without bot checks; empty = off
pot_provider_url = (os.environ.get('POT_PROVIDER_URL') or '').strip().rstrip('/')
# Shorts playback: 'youtube' = YouTube's own embedded player in the browser (no server download,
# no ads in single Shorts, near-zero server load); 'server' = download each Short as an MP4 here
shorts_player = 'server' if (os.environ.get('SHORTS_PLAYER') or 'youtube').strip().lower() == 'server' else 'youtube'

deprecated_env = ['DOWNLOAD_PATH', 'PROXY']

hls_duration = 5
hls_audio_duration = 10


os.makedirs(data_path, exist_ok=True)
print(f'Data path: {data_path}')
ffmpeg = None if disable_transcoding else External.download_ffmpeg()
if not ffmpeg and not disable_transcoding:
    raise RuntimeError("FFMPEG can not be detected nor installed in your system. Install FFMPEG or disable transcoding.")

js_runtime = External.download_deno()

ydl_global_opts = {'ffmpeg_location': ffmpeg, "noplaylist": True, 'playlistend': 0, "remote_components": ["ejs:github"], "concurrent_fragment_downloads": 2}
if js_runtime and 'deno' not in subprocess.check_output([js_runtime, '--version']).decode(): ydl_global_opts["js_runtimes"] = {"node": {}}
if impersonate_browser: ydl_global_opts["impersonate"] = impersonate_browser

app_version = External.get_app_version()



def _installed_ytdlp_version():
    try:
        import importlib, importlib.metadata
        importlib.invalidate_caches()
        return importlib.metadata.version('yt-dlp')
    except Exception:
        return None


def ytdlp_download():
    """Daily yt-dlp update. yt-dlp isn't hot-swapped inside running workers any more (that broke
    the PO token plugin), so when a new version was installed the server restarts itself during
    the night (03:00-05:00 server time) and Docker brings it straight back up with it."""
    while True:
        time.sleep(86400)  # the update at startup already ran
        before = _installed_ytdlp_version()
        print("Running periodic yt-dlp update")
        External.download_ytdlp()
        after = _installed_ytdlp_version()
        if after and after != before:
            print(f"yt-dlp updated {before} -> {after}; restarting between 03:00 and 05:00 to load it")
            while not (3 <= time.localtime().tm_hour < 5):
                time.sleep(600)
            print("Restarting to load the new yt-dlp")
            os.kill(os.getpid(), 15)


def delete_old_files():
    while True:
        print(f"Running periodic removal of old files")
        try:
            for item_name in os.listdir(data_path):
                vid_path = os.path.join(data_path, item_name)
                if not os.path.isdir(vid_path): continue

                keepalive_file = os.path.join(vid_path, 'keepalive')
                mtime = 0
                if os.path.exists(keepalive_file):
                    try:
                        with open(keepalive_file, 'r') as f:
                            mtime = int(f.read())
                    except Exception:
                        pass
                if time.time() - mtime > max_video_age:
                    print(f"Deleting old directory: {vid_path}")
                    shutil.rmtree(vid_path)

        except Exception as e:
            print(f"Error in delete_old_files: {e}")

        time.sleep(max_video_age / 2)



if __name__ == '__main__':

    for item_name in os.listdir(data_path):
        item = os.path.join(data_path, item_name)
        if not os.path.isdir(item): os.remove(item)

    Thread(target=delete_old_files, daemon=True).start()
    # update yt-dlp before the workers start, so they all import the new version once
    if os.environ.get('YTDLP_UPDATE_ON_START', 'true').lower() == 'true':
        print("Updating yt-dlp before starting")
        External.download_ytdlp()
    Thread(target=ytdlp_download, daemon=True).start()

    def pid_watcher():
        print(f"Watching process {linked_pid}")
        while True:
            time.sleep(1)
            if not psutil.pid_exists(linked_pid):
                print(f"Process {linked_pid} exited. Exiting.")
                os._exit(0)

    if linked_pid != 0: Thread(target=pid_watcher, daemon=True).start()

    if publish_with_cloudflare:
        External.publish_with_cf(port=port, app_title=app_title)

    import uvicorn
    if getattr(sys, 'frozen', False):
        from app import wsgi
        uvicorn.run(wsgi, host='0.0.0.0', port=port, workers=1, lifespan='off')
    else:
        # each worker loads its own yt-dlp (+ JS solver runs); 4 was too many for a 2 GB container
        uvicorn.run("app:wsgi", host='0.0.0.0', port=port, workers=max(1, int(os.environ.get('WORKERS', '2'))), lifespan='off')
