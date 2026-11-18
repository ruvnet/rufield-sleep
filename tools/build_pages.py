"""Create the static browser edition using the same UI as the local console."""
import argparse
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def build(target):
    target.mkdir(parents=True,exist_ok=True)
    for name in ("style.css","app.js","pages.js"):
        shutil.copy2(ROOT/"web"/name,target/name)
    html=(ROOT/"web/index.html").read_text()
    html=html.replace('<script defer src="./app.js">','<script defer src="./pages.js"></script>\n    <script defer src="./app.js">')
    html=html.replace('<meta name="theme-color"', '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; style-src \'self\'; img-src \'self\'; connect-src \'none\'; form-action \'none\'; base-uri \'none\'">\n    <meta name="theme-color"')
    (target/"index.html").write_text(html)
    (target/".nojekyll").touch()

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("target",type=Path)
    build(p.parse_args().target)
