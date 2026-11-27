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



def crop_icon(crop):
    """Three project-owned pictograms that remain distinct at toolbar size."""
    image = Image.new("RGBA", (96, 96))
    draw = ImageDraw.Draw(image)
    if crop == "wheat":
        draw.line([(24, 86), (43, 64), (69, 15)], fill="#507753", width=6)
        draw.polygon([(39, 70), (22, 64), (12, 53), (32, 56)], fill="#659566")
        for x, y in [(45, 65), (50, 54), (55, 43), (60, 32)]:
            draw.polygon(
                [(x, y), (x - 11, y - 3), (x - 16, y - 18), (x - 5, y - 13)],
                fill="#dcb358",
                outline="#a17736",
                width=2,
            )
            draw.polygon(
                [(x, y), (x + 13, y - 1), (x + 22, y - 12), (x + 10, y - 12)],
                fill="#e8c16b",
                outline="#a17736",
                width=2,
            )
        draw.polygon(
            [(63, 33), (59, 20), (71, 7), (74, 20)],
            fill="#e8c16b",
            outline="#a17736",
            width=2,
        )
    elif crop == "maize":
        draw.rounded_rectangle(
            (28, 8, 68, 77), radius=20, fill="#efbd55", outline="#a9762e", width=3
        )
        for row in range(19, 68, 11):
            for col in (34, 45, 56):
                draw.rounded_rectangle(
                    (col, row, col + 7, row + 6), radius=2, fill="#ffe095"
                )
        draw.polygon(
            [(49, 87), (28, 75), (18, 52), (17, 33), (35, 48), (47, 69)],
            fill="#659d69",
            outline="#497951",
            width=3,
        )
        draw.polygon(
            [(48, 87), (68, 75), (78, 51), (78, 34), (61, 49), (50, 68)],
            fill="#8ab581",
            outline="#497951",
            width=3,
        )
    else:
        draw.ellipse((26, 8, 67, 50), fill="#926140")
        draw.ellipse((26, 46, 70, 89), fill="#926140")
        draw.rectangle((34, 28, 61, 67), fill="#926140")
        draw.ellipse((29, 11, 64, 47), fill="#e2b77d")
        draw.ellipse((29, 49, 67, 86), fill="#e2b77d")
        draw.rectangle((37, 29, 58, 66), fill="#e2b77d")
        for x, y in [(35, 25), (38, 37), (40, 50), (35, 63), (37, 74)]:
            draw.line([(x, y), (x + 12, y + 4), (x + 23, y)], fill="#a87751", width=3)
        draw.line([(48, 17), (46, 35), (49, 54), (48, 79)], fill="#a87751", width=3)
        image = image.rotate(27, resample=Image.Resampling.BICUBIC)
    return image

if __name__=='__main__':
    (STATIC/'icons').mkdir(parents=True,exist_ok=True); (STATIC/'crops').mkdir(exist_ok=True)
    for crop in ['wheat','maize','peanut']:
        crop_icon(crop).save(STATIC/'icons'/f'{crop}.png', optimize=True)
    for crop in ['wheat','maize','peanut']:crop_art(crop).resize((240,276),Image.Resampling.LANCZOS).save(STATIC/'crops'/f'{crop}.png')
    print('Generated botanical illustrations; use npm run icons for UI icons')
