# CorelDRAW PDF-Konverter (3 mm Beschnitt)

Der Standardmodus `corel` bildet die Struktur der zuvor erfolgreichen `Eintrittskarte_Druck_3mm_Beschnitt.pdf` nach: neue PDF-Seite, durchgehende Hintergrundfarbe (aus der oberen linken Ecke ermittelt), unveraendert uebernommener Original-Vektorinhalt und 3 mm Beschnitt mit TrimBox/BleedBox.

**Wichtig:** Bei mehrfarbigen Raendern ist der automatisch ergaenzte Beschnitthintergrund ggf. unpassend. Der Import in beliebige CorelDRAW-Versionen ist nicht garantiert. Bereits in Kurven verwandelte Schrift wird dadurch nicht editierbar.

# PDF Beschnitt GUI

Eigenstaendige Desktopanwendung zum Erstellen einer Druck-PDF mit standardmaessig **3 mm Beschnitt**. Der Originalinhalt der PDF bleibt als Vektorinhalt erhalten; nur automatisch erstellte Randstreifen koennen rasterisiert werden.

**Windows:** Release ZIP entpacken und `PDF-Beschnitt-GUI.exe` im entpackten Ordner starten. Den gesamten Ordner inklusive `_internal` behalten.

**Linux:** Release TAR.GZ entpacken und `./PDF-Beschnitt-GUI` ausfuehren. Es ist kein Python/pip noetig; eine grafische Desktop-Sitzung und die ueblichen System-GUI-Bibliotheken werden benoetigt. Bei Bedarf: `chmod +x PDF-Beschnitt-GUI`.

## GitHub Actions

1. Alle Dateien dieses Projekts inklusive `.github/workflows/build.yml` in ein GitHub-Repository hochladen.
2. Auf **Actions > Build Windows and Linux > Run workflow** klicken, oder nach `main` pushen.
3. Nach erfolgreich durchgelaufenen Builds die TAR.GZ- und ZIP-Dateien unter **Artifacts** herunterladen.
4. Fuer eine automatische GitHub-Release-Version ein Tag wie `v1.0.0` pushen:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Das Release enthaelt beide Plattformarchive. GitHub Actions stellt Windows- und Linux-Binaries getrennt auf passenden Runnern her. Ein Build auf Linux erzeugt **keine** Windows-EXE durch Cross-Compiling.

## Lokal aus Quellcode starten

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python PDF_Beschnitt_GUI.py
```

Unter Ubuntu ggf. `sudo apt install python3-venv python3-tk` ausfuehren.

## CLI

```bash
python PDF_Beschnitt_GUI.py --input quelle.pdf --output druck.pdf --bleed 3 --mode stretch --dpi 300
```

## Grenzen

Das Verfahren setzt PDF TrimBox und BleedBox. Automatisch fortgesetzte oder gespiegelte Kanten koennen an Mustern sichtbar sein; Druckdaten unbedingt kontrollieren. Es findet keine PDF/X-Konvertierung oder automatische CMYK-Farbkonvertierung statt. Die Build-Workflows pruefen einen nicht-interaktiven Testexport, nicht die grafische Fensterdarstellung.


## Referenzgleicher CLI-Export

```bash
python PDF_Beschnitt_GUI.py --input original.pdf --output original_CorelDRAW_3mm.pdf --mode corel --bleed 3
```
