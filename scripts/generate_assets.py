"""Generate project-owned botanical illustrations and line icons."""
from pathlib import Path
import math
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "apps/client/src/static"
INK = "#326b49"


def leaf(draw, start, end, width, fill, outline=None):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1
    nx, ny = -dy / length * width, dx / length * width
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    points = [start, (middle[0] + nx, middle[1] + ny), end, (middle[0] - nx, middle[1] - ny)]
    draw.polygon(points, fill=fill)
    draw.line([start, end], fill=outline or "#668456", width=max(2, int(width / 12)))


def crop_art(crop, scale=1):
    im = Image.new("RGBA", (400, 460))
    draw = ImageDraw.Draw(im)
    if crop == "wheat":
        for offset, tilt, shade in [(-55, -22, "#b39b54"), (0, 0, "#c6ad64"), (52, 28, "#d0b971")]:
            x = 200 + offset
            draw.line([(x, 410), (x + tilt, 90)], fill="#7b9152", width=7)
            for y in range(110, 270, 25):
                center = x + tilt * ((410 - y) / 320)
                for side in (-1, 1):
                    leaf(draw, (center, y + 22), (center + side * 33, y - 12), 12, shade, "#a08f50")
                    draw.line([(center + side * 24, y - 6), (center + side * 43, y - 42)], fill="#d0bb7a", width=2)
            leaf(draw, (x, 355), (x - 53, 291), 16, "#758a4f")
            leaf(draw, (x, 385), (x + 57, 320), 16, "#8c9f61")
    elif crop == "maize":
        draw.line([(210, 420), (210, 85)], fill="#668b4e", width=8)
        for a,b,w,c in [((210,370),(70,210),38,"#6c9656"),((210,330),(343,170),34,"#87a965"),((210,250),(91,125),28,"#91ad70"),((210,190),(306,96),24,"#73954d")]:
            leaf(draw,a,b,w,c)
        draw.ellipse((176,184,245,340), fill="#d4b967", outline="#a78f49",width=3)
        for y in range(198,327,15):
            for x in range(186,238,14): draw.rounded_rectangle((x,y,x+10,y+11),radius=4,fill="#e4cc83",outline="#c3a65e",width=1)
        leaf(draw,(205,350),(160,240),21,"#6b914d")
        leaf(draw,(220,350),(262,230),20,"#8eaa61")
        for side in [-1,1]:
            draw.line([(210,110),(210+side*34,70)],fill="#bbab6c",width=3)
    else:
        draw.line([(200,405),(196,130)],fill="#7f9362",width=7)
        for y,side in [(170,-1),(205,1),(265,-1),(300,1)]:
            x=196+side*53
            draw.line([(198,y+30),(x,y)],fill="#6d8b4c",width=4)
            for sign in [-1,1]: leaf(draw,(x,y),(x+sign*58,y-45),36,"#8eab66" if side<0 else "#6b9356")
        draw.ellipse((140,355,195,418),fill="#ccb181",outline="#aa8c61",width=3)
        draw.ellipse((162,394,211,449),fill="#d9c397",outline="#aa8c61",width=3)
        for y in range(365,432,12): draw.line([(160,y),(190,y+7)],fill="#b89a6d",width=2)
    return im


def icon(name, color):
    im=Image.new("RGBA",(96,96)); d=ImageDraw.Draw(im); w=5
    def line(points): d.line([(x*2,y*2) for x,y in points],fill=color,width=w,joint="curve")
    def box(coords, radius=4): d.rounded_rectangle(tuple(c*2 for c in coords),radius=radius*2,outline=color,width=w)
    def ellipse(coords): d.ellipse(tuple(c*2 for c in coords),outline=color,width=w)
    if name=='camera':
        box((6,14,42,38)); line([(14,14),(18,8),(29,8),(33,14)]); ellipse((17,20,31,34))
    elif name=='upload':
        line([(8,30),(8,40),(40,40),(40,30)]);line([(24,32),(24,8),(14,18)]);line([(24,8),(34,18)])
    elif name=='leaf':
        d.polygon([(12,72),(20,28),(77,15),(72,59),(42,78)],outline=color,fill=None,width=w);line([(8,42),(33,17)]);line([(18,31),(18,21)]);line([(24,25),(34,26)])
    elif name=='wheat':
        line([(24,43),(24,5)])
        for y in [12,20,28]:line([(24,y+7),(14,y),(24,y+2),(34,y-5),(24,y+7)])
    elif name=='maize':
        ellipse((18,9,31,36));line([(24,42),(24,25)]);line([(24,37),(10,23),(17,40),(24,42),(39,22),(32,39),(24,42)]);line([(24,13),(24,30)])
    elif name=='peanut':
        line([(24,43),(24,12)]);ellipse((5,9,22,21));ellipse((25,9,43,21));ellipse((8,24,23,35));ellipse((25,24,40,35))
    elif name=='history':
        d.arc((15,12,84,84),30,320,fill=color,width=w);line([(7,11),(7,23),(19,23)]);line([(25,14),(25,26),(33,30)])
    elif name=='book':
        line([(24,12),(10,8),(5,10),(5,39),(12,37),(24,41),(36,37),(43,39),(43,10),(37,8),(24,12),(24,41)])
    elif name=='chevron':line([(14,19),(24,29),(34,19)])
    elif name=='arrow':line([(9,24),(39,24),(27,12)]);line([(39,24),(27,36)])
    elif name=='chat':box((6,8,42,34));line([(13,34),(13,42),(23,34)]);line([(14,18),(34,18)]);line([(14,25),(27,25)])
    elif name=='check':line([(9,25),(19,35),(40,13)])
    elif name=='plus':line([(24,9),(24,39)]);line([(9,24),(39,24)])
    elif name=='close':line([(13,13),(35,35)]);line([(35,13),(13,35)])
    elif name=='location':
        ellipse((9,5,39,35));line([(10,27),(24,44),(38,27)]);ellipse((19,15,29,25))
    elif name=='image':box((6,7,42,41));ellipse((13,13,21,21));line([(7,36),(20,23),(28,31),(35,25),(42,32)])
    elif name=='search' or name=='zoom':
        ellipse((7,6,32,31));line([(29,29),(42,42)])
        if name=='zoom':line([(12,19),(27,19)]);line([(20,11),(20,26)])
    elif name=='trash':line([(8,12),(40,12)]);box((12,13,36,41));line([(18,12),(18,6),(30,6),(30,12)]);line([(20,21),(20,34)]);line([(28,21),(28,34)])
    elif name=='settings':
        ellipse((9,9,39,39));ellipse((19,19,29,29))
        for a in range(0,360,45):
            r=math.radians(a);line([(24+15*math.cos(r),24+15*math.sin(r)),(24+21*math.cos(r),24+21*math.sin(r))])
    elif name=='info':ellipse((5,5,43,43));line([(24,21),(24,35)]);ellipse((23,12,25,14))
    return im.resize((64,64),Image.Resampling.LANCZOS)


if __name__=='__main__':
    (STATIC/'icons').mkdir(parents=True,exist_ok=True); (STATIC/'crops').mkdir(exist_ok=True)
    for name in ['camera','upload','leaf','wheat','maize','peanut','history','book','chevron','arrow','chat','check','plus','close','settings','location','image','search','info','trash','zoom']:
        for suffix,color in [('',INK),('-white','#ffffff')]:icon(name,color).save(STATIC/'icons'/f'{name}{suffix}.png')
    for crop in ['wheat','maize','peanut']:crop_art(crop).resize((240,276),Image.Resampling.LANCZOS).save(STATIC/'crops'/f'{crop}.png')
    field=Image.new('RGBA',(900,650))
    for i,(x,y,angle) in enumerate([(10,50,-18),(260,-60,9),(480,30,23)]):
        plant=crop_art('wheat').resize((360,530)).rotate(angle,expand=True,resample=Image.Resampling.BICUBIC)
        field.alpha_composite(plant,(x,y))
    field.save(STATIC/'field-art.png')
    print('Generated 42 icons and 4 botanical illustrations')
