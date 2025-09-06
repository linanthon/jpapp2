import subprocess, tempfile, os
from flask import Flask, request, send_file, abort

app = Flask(__name__)

@app.route("/tts")
def tts():
    word = request.args.get("word")
    if not word:
        return abort(400, "Missing ?word=")

    # make a temp wav file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp_path = tmp.name
    tmp.close()

    try:
        cmd = [
            "open_jtalk",
            "-x", "/var/lib/mecab/dic/open-jtalk/naist-jdic",
            "-m", "/usr/share/hts-voice/mei/mei_normal.htsvoice",
            "-ow", tmp_path,
        ]
        subprocess.run(cmd, input=word.encode("utf-8"), check=True)

        return send_file(tmp_path, mimetype="audio/wav")

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    app.run()
    