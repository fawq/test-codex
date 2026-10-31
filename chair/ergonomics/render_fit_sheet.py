"""Raster preview of this audit's simple SVG, using Matplotlib and Pillow.

python ergonomics/render_fit_sheet.py
This is a renderer for our own small drawing vocabulary, not a general SVG tool.
"""
import base64
import io
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

# Work in read-only home directories too, while preserving user-selected caches.
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'chair-fit-mpl'))
os.environ.setdefault('XDG_CACHE_HOME',str(Path(tempfile.gettempdir())/'chair-fit-cache'))
Path(os.environ['MPLCONFIGDIR']).mkdir(parents=True,exist_ok=True)
Path(os.environ['XDG_CACHE_HOME']).mkdir(parents=True,exist_ok=True)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from PIL import Image

here=Path(__file__).resolve().parent
root=ET.parse(here/'fit_200cm.svg').getroot()
width,height=float(root.attrib['width']),float(root.attrib['height'])
dpi=100
fig=plt.figure(figsize=(width/dpi,height/dpi),dpi=dpi)
ax=fig.add_axes([0,0,1,1])
ax.set(xlim=(0,width),ylim=(height,0))
ax.set_axis_off()
for elem in root.iter():
    tag=elem.tag.rsplit('}',1)[-1]
    a=elem.attrib
    if tag=='rect':
        ax.add_patch(Rectangle((float(a.get('x',0)),float(a.get('y',0))),
                              float(a['width']),float(a['height']),facecolor=a.get('fill','none')))
    elif tag=='image':
        data=base64.b64decode(a['href'].split(',',1)[1])
        im=Image.open(io.BytesIO(data))
        x,y,w,h=[float(a[k]) for k in ['x','y','width','height']]
        ax.imshow(im,extent=(x,x+w,y+h,y),zorder=1)
    elif tag=='polyline':
        points=[tuple(map(float,p.split(','))) for p in a['points'].split()]
        ax.plot(*zip(*points),color=a['stroke'],linewidth=float(a['stroke-width'])*72/dpi,zorder=3)
    elif tag=='circle':
        xy=float(a['cx']),float(a['cy'])
        # Separate fill and outline so translucent fill does not fade the outline.
        ax.add_patch(Circle(xy,float(a['r']),facecolor=a.get('fill','none'),edgecolor='none',
                            alpha=float(a.get('fill-opacity',1)),zorder=4))
        if 'stroke' in a:
            ax.add_patch(Circle(xy,float(a['r']),facecolor='none',edgecolor=a['stroke'],
                                linewidth=float(a['stroke-width'])*72/dpi,zorder=5))
    elif tag=='text':
        ax.text(float(a['x']),float(a['y']),''.join(elem.itertext()),
                fontsize=float(a['font-size'])*72/dpi,fontfamily='DejaVu Sans',
                fontweight=a.get('font-weight','normal'),color=a.get('fill','#263b37'),
                ha='center' if a.get('text-anchor')=='middle' else 'left',va='baseline',zorder=6)
fig.savefig(here/'fit_200cm.png',dpi=dpi)
plt.close(fig)
print('Saved',here/'fit_200cm.png')
