from geo import *
import json
cls_info={ # code: (label, color, opacity)
 'G':('Keine Dürre + ≥ 50 % nFK (kein Trockenstress) – beste Flächen','#1a9641',0.75),
 'W':('Keine Dürre im Oberboden','#a6d96a',0.65),
 'H':('Ungewöhnlich trocken, aber ≥ 50 % nFK','#d9ef8b',0.6),
 'J':('Dürre, aber ≥ 50 % nFK','#fee08b',0.35),
 'Y':('Ungewöhnlich trocken','#ffff66',0.35),
 'L':('Moderate Dürre','#fcd37f',0.35),
 'O':('Schwere Dürre','#ffaa00',0.4),
 'R':('Extreme Dürre','#e60000',0.4),
 'D':('Außergewöhnliche Dürre','#730000',0.45)}
runs={k:[] for k in cls_info}
for j,row in enumerate(G):
    i=0
    while i<len(row):
        c=row[i]; k=i
        while k+1<len(row) and row[k+1]==c: k+=1
        if c in runs:
            la0=lat(Y[j]+2); la1=lat(Y[j]-2)
            runs[c].append([round(la0,4),round(lon(X[i]-2),4),round(la1,4),round(lon(X[k]+2),4)])
        i=k+1
towns=[("Groß Schönebeck",52.905,13.566),("Joachimsthal",52.979,13.745),("Eberswalde",52.833,13.820),("Kloster Chorin",52.902,13.880),("Angermünde",53.016,13.997),("Templin",53.118,13.502),("Zehdenick",52.980,13.333),("Wandlitz",52.744,13.459),("Bernau",52.680,13.588),("Biesenthal",52.766,13.645),("Oderberg",52.866,14.043),("Liebenwalde",52.869,13.396)]
spots=[
 dict(name="① Westliche Schorfheide um Groß Schönebeck",lat=52.926,lon=13.583,txt="Größte zusammenhängende Fläche ohne Dürre UND mit ≥ 50 % nFK im Oberboden (ca. 140 km², zwischen etwa 52,86–52,98° N und 13,46–13,70° O, bis an das Westufer des Werbellinsees)."),
 dict(name="② Chorin – Parsteiner See – südl. Angermünde",lat=52.986,lon=13.995,txt="Zweite große Fläche ohne Dürre im Oberboden (ca. 90 km²), pflanzenverfügbares Wasser hier meist 40–50 % nFK. Buchenwälder, Moränenhügel, viele feuchte Senken."),
 dict(name="③ Kleine Inseln bei Joachimsthal / Grimnitzsee",lat=52.944,lon=13.756,txt="Einzelne Zellen ohne Dürre mit ≥ 50 % nFK."),
 dict(name="④ Nördlich von Joachimsthal (Richtung Friedrichswalde)",lat=52.994,lon=13.632,txt="Größere Fläche 'ungewöhnlich trocken', aber ≥ 50 % nFK – zweite Wahl."),
]
json.dump(dict(runs=runs,info=cls_info,towns=towns,spots=spots),open(__import__('os').path.join(__import__('os').path.dirname(__file__),'..','data','mapdata.json'),'w'),ensure_ascii=False)
print({k:len(v) for k,v in runs.items()})
