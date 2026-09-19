import webview
from pathlib import Path
import logging
import sys
from api import Api

logger = logging.getLogger(__name__)

def _get_runtime_root() -> Path:
	"""
	Return the root directory that contains bundled static assets.
	
	In development, this is the project root next to this file.
	In a PyInstaller executable, this is the temporary extraction root (_MEIPASS)
	that contains bundled files such as ui/dist.
	"""
	if getattr(sys, "frozen", False):
		return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
	return Path(__file__).parent

def main() -> None:

	runtime_root = _get_runtime_root()
	html_path = runtime_root / "ui" / "dist" / "index.html"
	if not html_path.exists():
		raise FileNotFoundError(f"UI build not found at: {html_path}")
	
	webview.create_window(
		title="PFIN-Dash",
		url=html_path.resolve().as_uri(),
		js_api=Api(),
		width=1920,
		height=1080,
		text_select=True,
	)
	webview.start(debug=False)

if __name__ == "__main__":

	logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    )
	main()
