import webview
from pathlib import Path
import logging
from api import Api

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent

def main() -> None:

	html_path = ROOT/ 'ui' / 'dist'
	
	webview.create_window(
		title="PFIN-Dash",
        url = f"{html_path}/index.html",
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
