"""Run command-line export against the packaged GUI binary without a display."""
import argparse
import subprocess
import tempfile
from pathlib import Path
import fitz

p = argparse.ArgumentParser()
p.add_argument('--executable', required=True)
args = p.parse_args()
exe = Path(args.executable).resolve()
assert exe.is_file(), exe
with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    src = folder / 'sample.pdf'
    dst = folder / 'sample_bleed.pdf'
    doc = fitz.open()
    page = doc.new_page(width=300, height=500)
    page.insert_text((30, 50), 'Test PDF 3mm')
    doc.save(src)
    doc.close()
    subprocess.run([str(exe), '--input', str(src), '--output', str(dst), '--bleed', '3', '--mode', 'corel'], check=True, timeout=120)
    with fitz.open(dst) as out:
        assert out.page_count == 1
        p = out[0]
        b = 3 * 72 / 25.4
        assert abs(p.rect.width - (300 + 2*b)) < 0.1
        assert abs(p.rect.height - (500 + 2*b)) < 0.1
        assert abs(p.trimbox.width - 300) < 0.1
        assert abs(p.trimbox.height - 500) < 0.1
        assert len(p.get_images()) == 0, 'Corel-Modus soll keine Beschnitt-Rasterbilder erzeugen'
        assert len(p.get_text().strip()) > 0, 'Originaltext als PDF-Inhalt nicht erhalten'
    print('Smoke test OK')
