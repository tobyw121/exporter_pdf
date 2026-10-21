#!/usr/bin/env python3
"""GUI zum Erzeugen einer Druck-PDF mit echtem Beschnittrand.

Installation: python -m pip install PyMuPDF Pillow
Start:        python PDF_Beschnitt_GUI.py
Optional CLI: python PDF_Beschnitt_GUI.py --input quelle.pdf --output druck.pdf

Das PDF-Original wird als Vektorinhalt erhalten. Nur die neu hinzugefuegten
Randstreifen werden bei den Modi 'Kanten fortsetzen' / 'Spiegeln' gerastert.
Es werden TrimBox (Endformat) und BleedBox (Gesamtformat) gesetzt.
"""
import argparse
import io
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import fitz
    from PIL import Image, ImageOps
except ImportError:
    fitz = None
    Image = None
    ImageOps = None

POINTS_PER_MM = 72 / 25.4
MODES = {
    'CorelDRAW-kompatibel (wie Referenz)': 'corel',
    'Kanten fortsetzen (Rasterrand)': 'stretch',
    'Rand spiegeln': 'mirror',
    'Weissen Rand einfuegen': 'white',
}


def _paste_bleed(page_out, original_page, inner, bleed, mode, dpi):
    """Fill the bleed around inner without flattening original vectors.

    Source edge pixels are used outside the trim area. Rendering raster only
    for the border is intentional: a PDF path cannot be extended automatically
    in a geometrically meaningful fashion.
    """
    if mode == 'white':
        return
    scale = dpi / 72.0
    pix = original_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    w, h = img.size
    # Convert bleed width into pixels for the temporary border image.
    bx = max(1, round(bleed * scale))
    by = bx
    if mode == 'stretch':
        canvas = Image.new('RGB', (w + 2*bx, h + 2*by), 'white')
        canvas.paste(img, (bx, by))
        canvas.paste(img.crop((0, 0, 1, h)).resize((bx, h)), (0, by))
        canvas.paste(img.crop((w-1, 0, w, h)).resize((bx, h)), (bx+w, by))
        canvas.paste(img.crop((0, 0, w, 1)).resize((w, by)), (bx, 0))
        canvas.paste(img.crop((0, h-1, w, h)).resize((w, by)), (bx, by+h))
        corners = [(0,0,0,0), (w-1,0,bx+w,0), (0,h-1,0,by+h), (w-1,h-1,bx+w,by+h)]
        for x, y, tx, ty in corners:
            color = img.getpixel((x, y))
            canvas.paste(color, (tx, ty, tx+bx, ty+by))
    elif mode == 'mirror':
        canvas = Image.new('RGB', (w + 2*bx, h + 2*by), 'white')
        canvas.paste(img, (bx, by))
        # Reflect the strips; handle even a source smaller than the bleed.
        xlen, ylen = min(bx, w), min(by, h)
        left = ImageOps.mirror(img.crop((0, 0, xlen, h))).resize((bx, h))
        right = ImageOps.mirror(img.crop((w-xlen, 0, w, h))).resize((bx, h))
        top = ImageOps.flip(img.crop((0, 0, w, ylen))).resize((w, by))
        bottom = ImageOps.flip(img.crop((0, h-ylen, w, h))).resize((w, by))
        canvas.paste(left, (0, by)); canvas.paste(right, (bx+w, by))
        canvas.paste(top, (bx, 0)); canvas.paste(bottom, (bx, by+h))
        for src, xy, flip_x, flip_y in [
            ((0,0,xlen,ylen),(0,0),True,True),
            ((w-xlen,0,w,ylen),(bx+w,0),True,True),
            ((0,h-ylen,xlen,h),(0,by+h),True,True),
            ((w-xlen,h-ylen,w,h),(bx+w,by+h),True,True),
        ]:
            tile = img.crop(src)
            if flip_x: tile = ImageOps.mirror(tile)
            if flip_y: tile = ImageOps.flip(tile)
            canvas.paste(tile.resize((bx, by)), xy)
    else:
        raise ValueError('Unbekannter Beschnittmodus: ' + mode)

    # Insert only the four external border strips, preserving the PDF vectors
    # and not introducing a full-page raster background under them.
    regions = [
        (canvas.crop((0, 0, w+2*bx, by)), fitz.Rect(0, 0, inner.width+2*bleed, bleed)),
        (canvas.crop((0, by+h, w+2*bx, h+2*by)), fitz.Rect(0, inner.y1, inner.width+2*bleed, inner.y1+bleed)),
        (canvas.crop((0, by, bx, by+h)), fitz.Rect(0, bleed, bleed, inner.y1)),
        (canvas.crop((bx+w, by, w+2*bx, by+h)), fitz.Rect(inner.x1, bleed, inner.x1+bleed, inner.y1)),
    ]
    for strip, rect in regions:
        mem = io.BytesIO()
        strip.save(mem, format='PNG')
        page_out.insert_image(rect, stream=mem.getvalue(), overlay=True)


def sample_corner_color(page):
    """Read the upper-left printed background color from the source PDF."""
    # The successful reference uses an unbroken color behind the copied PDF.
    # Render only a tiny corner for a simple, consistent sRGB sample.
    corner = fitz.Rect(0, 0, min(3, page.rect.width), min(3, page.rect.height))
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=corner, colorspace=fitz.csRGB, alpha=False)
    return tuple(pix.samples[i] / 255.0 for i in range(3))


def make_print_pdf(source, destination, bleed_mm=3.0, mode='corel', dpi=300, progress=None):
    if fitz is None or (mode != 'corel' and Image is None):
        raise RuntimeError('Fehlende Pakete. Bitte PyMuPDF und fuer Rasterränder Pillow installieren.')
    bleed_mm = float(bleed_mm)
    dpi = int(dpi)
    if not 0.1 <= bleed_mm <= 20:
        raise ValueError('Beschnitt muss zwischen 0,1 und 20 mm liegen.')
    if not 72 <= dpi <= 600:
        raise ValueError('DPI muss zwischen 72 und 600 liegen.')
    if mode not in MODES.values():
        raise ValueError('Ungueltiger Beschnittmodus.')
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    if source == destination:
        raise ValueError('Quelldatei darf nicht ueberschrieben werden.')
    if not source.is_file():
        raise FileNotFoundError(str(source))
    bleed = bleed_mm * POINTS_PER_MM
    document = fitz.open(str(source))
    output = fitz.open()
    try:
        if document.needs_pass:
            raise ValueError('Die Quelldatei ist passwortgeschuetzt.')
        if not document.page_count:
            raise ValueError('PDF enthaelt keine Seiten.')
        for i, source_page in enumerate(document):
            rect = source_page.rect
            # source_page.rect reflects visible page rotation / crop.
            # show_pdf_page copies the original PDF graphics as vectors.
            page = output.new_page(width=rect.width + 2*bleed, height=rect.height + 2*bleed)
            trim = fitz.Rect(bleed, bleed, bleed+rect.width, bleed+rect.height)
            if mode == 'corel':
                # Recreate the successful Eintrittskarte_Druck_3mm_Beschnitt.pdf
                # structure: solid full-sheet background + native vector PDF form.
                page.draw_rect(page.rect, color=None, fill=sample_corner_color(source_page))
            else:
                page.draw_rect(page.rect, color=None, fill=(1, 1, 1), overlay=False)
                _paste_bleed(page, source_page, trim, bleed, mode, dpi)
            page.show_pdf_page(trim, document, i, overlay=True, keep_proportion=False)
            page.set_trimbox(trim)
            page.set_bleedbox(page.mediabox)
            # CropBox / MediaBox are deliberately the whole sheet (incl. bleed).
            # ArtBox optional: trim bounding area.
            page.set_artbox(trim)
            if progress:
                progress(i+1, document.page_count)
        destination.parent.mkdir(parents=True, exist_ok=True)
        output.set_metadata({'title':'Druck-PDF mit Beschnitt', 'creator':'PDF Beschnitt GUI'})
        output.save(str(destination), garbage=4, deflate=True)
    finally:
        output.close()
        document.close()
    # Verify boxes and output count.
    with fitz.open(str(destination)) as check:
        assert check.page_count > 0
        assert all(abs(p.bleedbox.width - p.trimbox.width - 2*bleed) < 0.05 for p in check)
    return destination


class BleedApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PDF CorelDRAW Export - 3 mm Beschnitt')
        self.geometry('830x450')
        self.minsize(780, 430)
        self.configure(bg='#f5f7fa')
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.bleed = tk.StringVar(value='3')
        self.dpi = tk.StringVar(value='300')
        self.mode = tk.StringVar(value=list(MODES)[0])
        self.status = tk.StringVar(value='Bereit. Bitte eine PDF-Datei auswaehlen.')
        self._init_styles()
        self._build()

    def _init_styles(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#f5f7fa')
        style.configure('TLabel', background='#f5f7fa', foreground='#243047', font=('DejaVu Sans', 10))
        style.configure('Head.TLabel', font=('DejaVu Sans', 17, 'bold'), foreground='#15233b')
        style.configure('Sub.TLabel', foreground='#5c687e', font=('DejaVu Sans', 9))
        style.configure('TButton', padding=(12, 7))
        style.configure('Action.TButton', font=('DejaVu Sans', 11, 'bold'), padding=(15, 10))

    def _build(self):
        root = ttk.Frame(self, padding=24)
        root.pack(fill='both', expand=True)
        ttk.Label(root, text='PDF fuer CorelDRAW konvertieren', style='Head.TLabel').pack(anchor='w')
        ttk.Label(root, text='Referenz-Methode: neuer PDF-Container, Originalvektoren und 3 mm Beschnitt.', style='Sub.TLabel').pack(anchor='w', pady=(4, 20))
        self._file_line(root, 'Quelldatei (PDF)', self.source, self.pick_source)
        self._file_line(root, 'Ausgabedatei (PDF)', self.destination, self.pick_destination)
        settings = ttk.Frame(root)
        settings.pack(fill='x', pady=(14, 3))
        ttk.Label(settings, text='Beschnitt (mm)').grid(row=0, column=0, sticky='w', padx=(0, 16))
        ttk.Label(settings, text='Exportmodus').grid(row=0, column=1, sticky='w', padx=(0, 16))
        ttk.Label(settings, text='Rand-DPI').grid(row=0, column=2, sticky='w')
        ttk.Entry(settings, textvariable=self.bleed, width=12).grid(row=1, column=0, sticky='w', padx=(0, 16), pady=5)
        ttk.Combobox(settings, textvariable=self.mode, values=list(MODES), state='readonly', width=39).grid(row=1, column=1, sticky='w', padx=(0, 16), pady=5)
        ttk.Combobox(settings, textvariable=self.dpi, values=['150','200','300','450','600'], state='readonly', width=9).grid(row=1, column=2, sticky='w', pady=5)
        ttk.Label(root, text='CorelDRAW-Modus: nutzt die Eckfarbe als Beschnitthintergrund.\nBei mehrfarbigem Rand die erzeugte Datei vor dem Druck kontrollieren.', style='Sub.TLabel').pack(anchor='w', pady=(9, 12))
        self.bar = ttk.Progressbar(root, maximum=100, mode='determinate')
        self.bar.pack(fill='x', pady=(5, 7))
        ttk.Label(root, textvariable=self.status, style='Sub.TLabel').pack(anchor='w')
        self.export_button = ttk.Button(root, text='Fuer CorelDRAW exportieren', style='Action.TButton', command=self.export)
        self.export_button.pack(anchor='e', pady=(13, 0))

    def _file_line(self, parent, heading, variable, callback):
        ttk.Label(parent, text=heading).pack(anchor='w', pady=(0, 4))
        line = ttk.Frame(parent)
        line.pack(fill='x', pady=(0, 10))
        ttk.Entry(line, textvariable=variable).pack(side='left', fill='x', expand=True, padx=(0, 10))
        ttk.Button(line, text='Durchsuchen...', command=callback).pack(side='right')

    def pick_source(self):
        selected = filedialog.askopenfilename(title='PDF-Datei auswaehlen', filetypes=[('PDF Dateien', '*.pdf')])
        if selected:
            self.source.set(selected)
            self.destination.set(str(Path(selected).with_name(Path(selected).stem + '_Druck_3mm_Beschnitt.pdf')))

    def pick_destination(self):
        selected = filedialog.asksaveasfilename(title='Druck-PDF speichern', defaultextension='.pdf', filetypes=[('PDF Dateien', '*.pdf')], initialfile=Path(self.destination.get()).name if self.destination.get() else 'Druck_3mm_Beschnitt.pdf')
        if selected:
            self.destination.set(selected)

    def export(self):
        src, dst = self.source.get().strip(), self.destination.get().strip()
        if not src or not dst:
            messagebox.showwarning('Datei fehlt', 'Bitte Eingabe- und Ausgabedatei auswaehlen.')
            return
        try:
            bleed = float(self.bleed.get().replace(',', '.'))
            dpi = int(self.dpi.get())
            mode = MODES[self.mode.get()]
        except (ValueError, KeyError):
            messagebox.showerror('Einstellungen', 'Ungueltige Einstellungen.')
            return
        if Path(dst).exists() and not messagebox.askyesno('Ueberschreiben?', f'Vorhandene Datei ueberschreiben?\n{dst}'):
            return
        self.export_button.configure(state='disabled')
        self.bar['value'] = 0
        self.status.set('Export laeuft ...')
        def report(i, total):
            self.after(0, lambda: (self.bar.configure(value=100*i/total), self.status.set(f'Seite {i} von {total} verarbeitet')))
        def work():
            try:
                result = make_print_pdf(src, dst, bleed, mode, dpi, report)
            except Exception as exc:
                self.after(0, lambda msg=str(exc): self._finished(False, msg))
            else:
                self.after(0, lambda: self._finished(True, str(result)))
        threading.Thread(target=work, daemon=True).start()

    def _finished(self, success, msg):
        self.export_button.configure(state='normal')
        if success:
            self.bar['value'] = 100
            self.status.set('Fertig: ' + msg)
            messagebox.showinfo('Export abgeschlossen', 'Druck-PDF erfolgreich erstellt:\n' + msg)
        else:
            self.status.set('Export fehlgeschlagen.')
            messagebox.showerror('Export fehlgeschlagen', msg)


def main():
    parser = argparse.ArgumentParser(description='GUI: PDF wie die erfolgreiche CorelDRAW-Referenz mit 3 mm Beschnitt konvertieren')
    parser.add_argument('--input', help='Quelldatei fuer Kommandozeilenmodus')
    parser.add_argument('--output', help='Zieldatei fuer Kommandozeilenmodus')
    parser.add_argument('--bleed', type=float, default=3.0, help='Beschnitt in Millimetern (Standard: 3)')
    parser.add_argument('--mode', choices=['corel', 'stretch', 'mirror', 'white'], default='corel')
    parser.add_argument('--dpi', type=int, default=300)
    args = parser.parse_args()
    if args.input or args.output:
        if not (args.input and args.output):
            parser.error('--input und --output werden zusammen benoetigt')
        print(make_print_pdf(args.input, args.output, args.bleed, args.mode, args.dpi))
    else:
        if fitz is None or Image is None:
            print('Abhaengigkeiten fehlen: python -m pip install PyMuPDF Pillow')
            return
        BleedApp().mainloop()


if __name__ == '__main__':
    main()
