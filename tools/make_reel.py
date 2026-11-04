# rifa il video di Scan Studio: voce (say), registrazioni dell interfaccia vera (tools/reel), didascalie di vetro (ffmpeg)
# uso: avviare lo studio su una copia di prova (porta 8799), poi DEMO=<copia> python3 -I tools/make_reel.py
import os, subprocess, json, shutil, sys, time
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.expanduser('~/Scans/.scancut')
REEL = os.path.join(REPO, 'tools', 'reel')
FF = '/opt/miniconda3/bin/ffmpeg'
FP = '/opt/miniconda3/bin/ffprobe'
W, H, FPS = 1280, 800, 12
URL = 'http://127.0.0.1:8799/'
VOICE, RATE = 'Fred', '172'
SK = 'originals%2Fsk%2Fsk%201.jpg'
CARD = 'originals%2Fcard%2Fcard%201.png'

# (name, url, caption, narration, js)
SCENES = [
 ('gallery', URL, 'Scans land in a folder. Open one.',
  'Scans land in a folder. You open one.',
  "(async()=>{await sleep(900); openDir('originals/sk'); await sleep(1600); const t=document.querySelector('.thumb'); t&&t.classList.add('sel'); await sleep(900); openScan('originals/sk/sk 1.jpg');})();"),
 ('otsu', URL + '#' + SK, 'Pick a method. Here: Otsu threshold, edge from real pixels.',
  'Pick a method. Otsu threshold. Classic lid colour. Apple Vision. Or SAM 3 on the local GPU.',
  "(async()=>{await ready(); await sleep(500); S.engine='otsu'; renderSide(); await sleep(1200); detect(null,'otsu');})();"),
 ('loupe', URL + '#' + SK, 'Densitometer and loupe: the real values under the cursor.',
  'Only transparency changes. Nothing is painted. The densitometer and the loupe show the real values under the cursor.',
  "(async()=>{await ready(); S.loupe=true; for(let i=0;i<6;i++){zoomAt(1.32,...toScr(820,1450)); await sleep(60);} await sleep(300); for(const p of [[840,1300],[812,1450],[790,1600]]){const [sx,sy]=toScr(...p); mouse=p; measure(p,sx,sy); await sleep(1100);} })();"),
 ('wand', URL + '#' + SK, 'Magic Wand, Intersect, Contiguous off: only the ink inside the page.',
  'Magic wand. Intersect. Contiguous off. Only the ink inside the page.',
  "(async()=>{await ready(); setTool('wand'); S.wandContig=false; S.wandTol=60; setMode('int'); S.selSheet=S.st.sheets[0].id; renderSide(); draw(); await sleep(1500); await wandAt([1188,900],'int'); await sleep(1500); cutoutDialog(S.st.sheets[0]);})();"),
 ('sam', URL + '#' + SK, 'SAM 3: a text prompt, then click the object you want.',
  'SAM 3. A text prompt. Click the object you want.',
  "(async()=>{await ready(); S.engine='sam3'; S.params.prompt='sheet of paper'; renderSide(); setTool('sam'); await sleep(1300); samClick([1500,3000],true);})();"),
 ('corner', URL + '#' + CARD, 'Format from a corner: an exact A5 from the bottom left. No detection. Batch it.',
  'Fixed formats from a corner. A5, bottom left. No detection. Batch it.',
  "(async()=>{await ready(); S.engine='corner'; S.params.format='A5'; renderSide(); await sleep(1300); detect(null,'corner'); await sleep(1800); cutoutDialog(S.st.sheets.at(-1));})();"),
 ('scanner', URL, 'The scanner, through SANE: bed preview, areas, real resolutions, 48-bit capable.',
  'The scanner is driven through sane. Forty eight bit capable. Draw the areas. Scan.',
  "(async()=>{await sleep(600); go('scanners'); for(let i=0;i<40 && !SC.dev;i++) await sleep(250); await sleep(600); addArea(148,210); SC.areas[0][0]=30; SC.areas[0][1]=40; drawBed(); renderScanSide(); await sleep(900); addArea(105,148); SC.areas[1][0]=105; SC.areas[1][1]=140; drawBed(); renderScanSide();})();"),
 ('export', URL + '#' + SK, 'Export: PNG or lossless JPEG XL. Metadata and true size kept, 1:1.',
  'Export. P N G, or lossless J P E G X L. Metadata and true size are kept. One to one.',
  "(async()=>{await ready(); await api.post('settings',{export_format:'jxl'}); S.settings=await api.get('settings'); renderSide(); await sleep(900); doExport();})();"),
]
INTRO = ('Scan Studio', 'cut scanned drawings off the scanner bed · macOS · local · open source',
         'Scan Studio. A tool for cutting scanned drawings off the scanner bed. It runs on your Mac. No account. No cloud.')
OUTRO = ('github.com/aallevi/scancut', 'MIT licence · no telemetry · no account',
         'Source on github. M I T. That is it.')

FONT = '/System/Library/Fonts/Supplemental/Tahoma.ttf'
FONTB = '/System/Library/Fonts/Supplemental/Tahoma Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        print(' '.join(cmd)[:300]); print(r.stderr[-2000:]); sys.exit(1)
    return r.stdout


def dur(f):
    return float(run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).strip())


def voice(text, out):
    run(['say', '-v', VOICE, '-r', RATE, '-o', out + '.aiff', text])
    run([FF, '-y', '-v', 'error', '-i', out + '.aiff', '-ar', '48000', '-ac', '2', out])
    return dur(out)


def caption_png(text, out, y=H - 118, h=78):
    # the glass panel over the blurred band: white veil, light rim, Aero streak, text with a soft glow
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, x1 = 60, W - 60
    d.rounded_rectangle([x0, y, x1, y + h], 12, fill=(255, 255, 255, 70), outline=(255, 255, 255, 170), width=2)
    streak = Image.new('RGBA', (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(streak)
    sd.polygon([(x0 + 120, y), (x0 + 260, y), (x0 + 200, y + h), (x0 + 60, y + h)], fill=(255, 255, 255, 38))
    mask = Image.new('L', (W, H), 0); ImageDraw.Draw(mask).rounded_rectangle([x0, y, x1, y + h], 12, fill=255)
    im.alpha_composite(Image.composite(streak, Image.new('RGBA', (W, H), (0, 0, 0, 0)), mask))
    f = ImageFont.truetype(FONT, 25)
    tw = d.textlength(text, font=f)
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text(((W - tw) / 2, y + h / 2 - 15), text, font=f, fill=(255, 255, 255, 230))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4)))
    ImageDraw.Draw(im).text(((W - tw) / 2, y + h / 2 - 15), text, font=f, fill=(12, 22, 36, 255))
    im.save(out)
    m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).rounded_rectangle([x0, y, x1, y + h], 12, fill=255)
    m.save(out.replace('.png', '_mask.png'))


def card(title, sub, out, bg):
    # title cards: the app, blurred, behind a big glass panel
    base = Image.open(bg).convert('RGB').resize((W, H)).filter(ImageFilter.GaussianBlur(16))
    base = Image.blend(base, Image.new('RGB', (W, H), (8, 30, 48)), 0.45).convert('RGBA')
    pan = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(pan)
    box = [180, 270, W - 180, 530]
    d.rounded_rectangle(box, 16, fill=(255, 255, 255, 46), outline=(255, 255, 255, 150), width=2)
    d.polygon([(box[0] + 160, box[1]), (box[0] + 330, box[1]), (box[0] + 230, box[3]), (box[0] + 60, box[3])], fill=(255, 255, 255, 22))
    base.alpha_composite(pan)
    d = ImageDraw.Draw(base)
    ft, fs = ImageFont.truetype(FONTB, 52), ImageFont.truetype(FONT, 22)
    for txt, f, yy, col in ((title, ft, 345, (255, 255, 255)), (sub, fs, 432, (214, 232, 246))):
        tw = d.textlength(txt, font=f)
        gl = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(gl).text(((W - tw) / 2, yy), txt, font=f, fill=(120, 190, 255, 180))
        base.alpha_composite(gl.filter(ImageFilter.GaussianBlur(8)))
        ImageDraw.Draw(base).text(((W - tw) / 2, yy), txt, font=f, fill=col)
    base.convert('RGB').save(out)


def fill_gaps(frames):
    # i fotogrammi hanno il numero del loro istante: dove manca un istante si ripete il precedente,
    # cosi' la scena dura il tempo vero
    have = sorted(int(f[1:6]) for f in os.listdir(frames) if f.endswith('.jpg'))
    last = None
    for i in range(0, have[-1] + 1):
        f = os.path.join(frames, f'f{i:05d}.jpg')
        if os.path.exists(f):
            last = f
        elif last:
            shutil.copy(last, f)
        else:
            shutil.copy(os.path.join(frames, f'f{have[0]:05d}.jpg'), f)


def scene_video(frames, cap, audio, out, seconds):
    fill_gaps(frames)
    # frames -> video of the narration length (last frame held), blurred band under the glass caption
    fc = ('[0:v]fps=24,scale=%d:%d,setsar=1,tpad=stop_mode=clone:stop_duration=30,trim=duration=%.2f,setpts=PTS-STARTPTS,split[a][b];'
          '[b]crop=%d:%d:0:%d,gblur=sigma=14[bl];[2:v]format=gray,crop=%d:%d:0:%d[m];[bl][m]alphamerge[blm];'
          '[a][blm]overlay=0:%d[c];[c][1:v]overlay=0:0,format=yuv420p[v]') % (W, H, seconds, W, 78, H - 118, W, 78, H - 118, H - 118)
    run([FF, '-y', '-v', 'error', '-framerate', str(FPS), '-pattern_type', 'glob', '-i', os.path.join(frames, '*.jpg'),
         '-i', cap, '-i', cap.replace('.png', '_mask.png'), '-i', audio,
         '-filter_complex', fc, '-map', '[v]', '-map', '3:a', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
         '-c:a', 'aac', '-b:a', '128k', '-t', '%.2f' % seconds, out])


def still_video(img, audio, out, seconds):
    run([FF, '-y', '-v', 'error', '-loop', '1', '-i', img, '-i', audio, '-vf', 'fps=24,format=yuv420p,fade=t=in:st=0:d=0.5',
         '-c:v', 'libx264', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', '-t', '%.2f' % seconds, out])


def main(only=None):
    work = os.path.join(HERE, 'work'); os.makedirs(work, exist_ok=True)
    if not only:
        # demo pulito: niente stato, ritagli o impostazioni della volta prima (la cache resta: SAM e' gia' caldo)
        demo = os.environ['DEMO']
        for d in ('cut',):
            shutil.rmtree(os.path.join(demo, d), ignore_errors=True); os.makedirs(os.path.join(demo, d))
        shutil.rmtree(os.path.join(demo, '.scancut/studio-data/state'), ignore_errors=True)
        os.makedirs(os.path.join(demo, '.scancut/studio-data/state'))
        sp = os.path.join(demo, '.scancut/studio-data/settings.json')
        if os.path.exists(sp): os.remove(sp)
    parts = []
    for i, (name, url, cap, nar, js) in enumerate(SCENES):
        if only and name not in only:
            parts.append(os.path.join(work, f'{i:02d}_{name}.mp4')); continue
        a = os.path.join(work, f'{name}.wav'); secs = voice(nar, a) + 0.9
        jsf = os.path.join(work, f'{name}.js'); open(jsf, 'w').write("const sleep=t=>new Promise(r=>setTimeout(r,t)); const ready=async()=>{for(let i=0;i<150&&!(S.info&&V.img);i++) await sleep(100); await sleep(250);};" + js + " 'ok'")
        fr = os.path.join(work, 'frames_' + name); shutil.rmtree(fr, ignore_errors=True)
        print(name, f'{secs:.1f}s', run([REEL, url, fr, str(W), str(H), '%.1f' % (secs + 0.4), str(FPS), jsf]).strip())
        cp = os.path.join(work, f'{name}_cap.png'); caption_png(cap, cp)
        out = os.path.join(work, f'{i:02d}_{name}.mp4'); scene_video(fr, cp, a, out, secs); parts.append(out)
    bg = sorted(os.listdir(os.path.join(work, 'frames_otsu')))[-1]
    for nm, (t, sub, nar) in (('intro', INTRO), ('outro', OUTRO)):
        a = os.path.join(work, f'{nm}.wav'); secs = voice(nar, a) + 1.0
        img = os.path.join(work, f'{nm}.png'); card(t, sub, img, os.path.join(work, 'frames_otsu', bg))
        still_video(img, a, os.path.join(work, f'{nm}.mp4'), secs)
    lst = os.path.join(work, 'list.txt')
    open(lst, 'w').write(''.join(f"file '{p}'\n" for p in [os.path.join(work, 'intro.mp4')] + parts + [os.path.join(work, 'outro.mp4')]))
    out = os.path.join(REPO, 'media', 'scan-studio-reel.mp4'); os.makedirs(os.path.dirname(out), exist_ok=True)
    run([FF, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c:v', 'libx264', '-crf', '20', '-preset', 'slow',
         '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out])
    print('reel:', out, f'{dur(out):.1f}s')


if __name__ == '__main__':
    main(sys.argv[1:] or None)
