// Im Browser auf einer Seite von https://files.ufz.de/~drought/ ausführen (gleiche Origin, sonst Canvas "tainted").
// Liefert ein lauflängenkodiertes Raster (Zeilen mit '|' getrennt) für den Pixelausschnitt x 693–1000, y 150–420, Schritt 4 px.
async function load(u){const im=new Image();im.src=u;await im.decode();const c=document.createElement('canvas');c.width=im.width;c.height=im.height;const x=c.getContext('2d');x.drawImage(im,0,0);return x.getImageData(0,0,im.width,im.height);}
const SMm={'255,255,255':'W','255,255,0':'Y','252,211,127':'L','255,170,0':'O','230,0,0':'R','115,0,0':'D'};
const PM={'211,239,202':1,'145,215,198':1,'128,128,128':'i'};
const s=await load('/~drought/SM_0_25cm_dry-wet_aktuell_BE-BB.png'),p=await load('/~drought/PAW_0_25cm_dry-wet_aktuell_BE-BB.png');
const key=(d,x,y)=>{const i=(y*d.width+x)*4;return d.data[i]+','+d.data[i+1]+','+d.data[i+2]};
const pawIn=(x,y)=>{const k=key(p,x,y);return k!=='255,255,255'&&!(p.data[(y*p.width+x)*4]<120)};
let rows=[];for(let y=150;y<=420;y+=4){let r='',prev=null,n=0;for(let x=693;x<=1000;x+=4){let ch='.';
for(const [dx,dy] of [[0,0],[1,1],[-1,-1],[2,0],[0,2],[-2,0],[0,-2]]){const k=key(s,x+dx,y+dy);let c=SMm[k];if(!c)continue;
 if(c==='W'&&!pawIn(x+dx,y+dy))c='_';const pk=PM[key(p,x+dx,y+dy)];if(pk===1)c={W:'G',Y:'H'}[c]||(c==='_'?'_':'J');ch=c;break}
if(ch===prev)n++;else{if(prev)r+=prev+(n>1?n:'');prev=ch;n=1}}r+=prev+(n>1?n:'');rows.push(r)}
rows.join('|');
