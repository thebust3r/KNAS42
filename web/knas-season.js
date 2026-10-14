/* KNAS holiday skins: falling snow, leaves, hearts... plus a little animation when you change
   channel (a bat for Halloween, a sleigh for Christmas, fireworks for the Fourth...).
   Turned on by SEASON in settings (auto = by the calendar). */
(function(){
"use strict";
var K=window.KNAS||{},S=K.season||{};
if(!S.name||S.effects==="off")return;
var lite=document.documentElement.classList.contains("lite"),light=S.effects==="light"||lite;
var stage,cv,ctx,W=640,H=480,parts=[],fx=[],last=0,running=true,t0=performance.now();
/* in the cable box the falling stuff only shows while the TV guide is open, never over a show */
var showParts=(K.page||document.documentElement.getAttribute("data-page"))!=="tv";
var R=Math.random;function rnd(a,b){return a+R()*(b-a)}

/* ---------- what falls for each holiday ---------- */
var KIND={halloween:"bats",thanksgiving:"leaves",christmas:"snow",winter:"snow",newyear:"confetti",valentines:"hearts",stpatricks:"clovers",easter:"petals",july4:"stars"};
var kind=KIND[S.name]||"snow";
var COUNT={snow:70,leaves:22,confetti:45,hearts:18,clovers:20,petals:26,stars:30,bats:6}[kind];
if(light)COUNT=Math.ceil(COUNT/2.5);

function spawn(top){var p={x:rnd(0,W),y:top?rnd(-H,0):rnd(0,H),r:rnd(.6,1.4),a:rnd(0,6.28),va:rnd(-.03,.03),sw:rnd(0,6.28)};
  if(kind==="snow"){p.vy=rnd(.35,1.1);p.vx=0;p.size=rnd(1.2,3.4)}
  else if(kind==="leaves"){p.vy=rnd(.5,1.1);p.size=rnd(5,9);p.c=["#d9531e","#e8902a","#b5341c","#c9a227","#8a4b1a"][R()*5|0];p.va=rnd(-.05,.05)}
  else if(kind==="confetti"){p.vy=rnd(.8,1.8);p.size=rnd(3,6);p.c=["#ffd700","#ff4d6d","#4dd2ff","#7dff8a","#ffffff","#c77dff"][R()*6|0];p.va=rnd(-.15,.15)}
  else if(kind==="hearts"){p.vy=-rnd(.3,.8);p.y=top?rnd(H,H*2):rnd(0,H);p.size=rnd(5,10);p.c=["#ff5c8a","#ff8fb8","#ff2e63","#ffc2d6"][R()*4|0]}
  else if(kind==="clovers"){p.vy=rnd(.4,.9);p.size=rnd(4,7);p.c=["#1fbf4a","#3ad15a","#0f9a36"][R()*3|0];p.va=rnd(-.04,.04)}
  else if(kind==="petals"){p.vy=rnd(.4,.9);p.size=rnd(3,6);p.c=["#ffd1e8","#fff3a8","#c9f2c7","#d9c6ff","#ffffff"][R()*5|0];p.va=rnd(-.06,.06)}
  else if(kind==="stars"){p.vy=0;p.size=rnd(1,2.6);p.y=rnd(0,H*.6);p.tw=rnd(0,6.28);p.c=["#ffffff","#ff4d4d","#5fa8ff"][R()*3|0]}
  else if(kind==="bats"){p.vy=0;p.x=rnd(0,W);p.y=rnd(20,H*.45);p.vx=rnd(.4,1)*(R()<.5?-1:1);p.size=rnd(6,10);p.flap=rnd(0,6.28)}
  return p}

/* ---------- drawing ---------- */
function heart(x,y,s,c){ctx.fillStyle=c;ctx.beginPath();ctx.moveTo(x,y+s*.3);ctx.bezierCurveTo(x,y,x-s,y,x-s,y+s*.35);ctx.bezierCurveTo(x-s,y+s*.8,x,y+s*1.05,x,y+s*1.3);
  ctx.bezierCurveTo(x,y+s*1.05,x+s,y+s*.8,x+s,y+s*.35);ctx.bezierCurveTo(x+s,y,x,y,x,y+s*.3);ctx.fill()}
function bat(x,y,s,flap,c){var w=Math.sin(flap)*.6;ctx.fillStyle=c||"#140a1f";ctx.beginPath();ctx.moveTo(x,y);
  ctx.quadraticCurveTo(x-s*.9,y-s*(.9+w),x-s*2,y-s*w*.6);ctx.quadraticCurveTo(x-s*1.4,y+s*.1,x-s*1.1,y+s*.5);ctx.quadraticCurveTo(x-s*.6,y+s*.15,x,y+s*.55);
  ctx.quadraticCurveTo(x+s*.6,y+s*.15,x+s*1.1,y+s*.5);ctx.quadraticCurveTo(x+s*1.4,y+s*.1,x+s*2,y-s*w*.6);ctx.quadraticCurveTo(x+s*.9,y-s*(.9+w),x,y);ctx.fill();
  ctx.beginPath();ctx.arc(x,y+s*.15,s*.32,0,6.28);ctx.fill()}
function clover(x,y,s,c){ctx.fillStyle=c;for(var i=0;i<3;i++){var a=i*2.09-1.57;ctx.beginPath();ctx.arc(x+Math.cos(a)*s*.55,y+Math.sin(a)*s*.55,s*.5,0,6.28);ctx.fill()}
  ctx.strokeStyle=c;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+s*.3,y+s*1.2);ctx.stroke()}
function drawPart(p,t){
  ctx.save();
  if(kind==="snow"){ctx.globalAlpha=.85;ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(p.x,p.y,p.size,0,6.28);ctx.fill()}
  else if(kind==="leaves"||kind==="petals"){ctx.translate(p.x,p.y);ctx.rotate(p.a);ctx.fillStyle=p.c;ctx.beginPath();ctx.ellipse(0,0,p.size,p.size*.5,0,0,6.28);ctx.fill();
    if(kind==="leaves"){ctx.strokeStyle="rgba(60,25,5,.6)";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(-p.size,0);ctx.lineTo(p.size,0);ctx.stroke()}}
  else if(kind==="confetti"){ctx.translate(p.x,p.y);ctx.rotate(p.a);ctx.fillStyle=p.c;ctx.fillRect(-p.size/2,-p.size/4,p.size,p.size/2*Math.abs(Math.cos(p.a*2))+1)}
  else if(kind==="hearts"){ctx.globalAlpha=.85;heart(p.x,p.y,p.size,p.c)}
  else if(kind==="clovers"){ctx.translate(p.x,p.y);ctx.rotate(p.a);clover(0,0,p.size,p.c)}
  else if(kind==="stars"){ctx.globalAlpha=.4+.6*Math.abs(Math.sin(p.tw+t/700));ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,p.size,0,6.28);ctx.fill()}
  else if(kind==="bats"){ctx.globalAlpha=.85;bat(p.x,p.y,p.size,p.flap)}
  ctx.restore()}
function step(p,dt){
  p.sw+=.02*dt;p.a+=p.va*dt;
  if(kind==="bats"){p.x+=p.vx*dt;p.y+=Math.sin(p.sw)*.5*dt;p.flap+=.35*dt;if(p.x<-30||p.x>W+30){var q=spawn();q.x=p.vx>0?-20:W+20;q.vx=p.vx;Object.assign(p,q)}return}
  if(kind==="stars"){p.tw+=.01*dt;return}
  p.y+=p.vy*dt;p.x+=(Math.sin(p.sw)*.4+(p.vx||0))*dt;
  if(p.vy>0&&p.y>H+12)Object.assign(p,spawn(true),{y:-10});
  if(p.vy<0&&p.y<-14)Object.assign(p,spawn(true),{y:H+10})}

/* ---------- little extras that stay on screen ---------- */
function decor(t){
  if(S.name==="christmas"){var n=Math.round(W/46);for(var i=0;i<n;i++){var x=23+i*46,y=6+Math.sin(i*1.3)*3,on=((i+Math.floor(t/600))%3)===0;
      ctx.strokeStyle="#1d3a12";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x-23,6+Math.sin((i-1)*1.3)*3);ctx.quadraticCurveTo(x-11,14,x,y);ctx.stroke();
      ctx.fillStyle=["#ff3b3b","#ffd23a","#3bff6a","#3bb7ff"][i%4];ctx.globalAlpha=on?1:.45;ctx.beginPath();ctx.ellipse(x,y+6,3.5,5,0,0,6.28);ctx.fill();ctx.globalAlpha=1}}
  if(S.name==="halloween"){ctx.save();ctx.strokeStyle="rgba(230,230,240,.35)";ctx.lineWidth=1;var cx=W,cy=0;
    for(var k=0;k<6;k++){var a=Math.PI/2+k*(Math.PI/2)/5;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(a)*90,cy+Math.sin(a)*90);ctx.stroke()}
    for(var r=18;r<=90;r+=18){ctx.beginPath();for(var k2=0;k2<=5;k2++){var a2=Math.PI/2+k2*(Math.PI/2)/5,px=cx+Math.cos(a2)*r,py=cy+Math.sin(a2)*r;k2?ctx.quadraticCurveTo((px+cx)/2+(px-cx)*.08,(py+cy)/2,px,py):ctx.moveTo(px,py)}ctx.stroke()}
    ctx.restore()}}

/* ---------- channel-change animations ---------- */
function burst(x,y,colors,n,speed,shape){for(var i=0;i<n;i++){var a=rnd(0,6.28),v=rnd(speed*.4,speed);fx.push({k:"spark",x:x,y:y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,life:1,c:colors[i%colors.length],s:rnd(2,4),shape:shape})}}
function onTune(){if(!S.tune)return;var n=S.name;
  if(n==="halloween")fx.push({k:"bigbat",x:W+60,y:H*.55,t:0});
  else if(n==="christmas"||n==="winter")fx.push({k:"sleigh",x:-160,y:60,t:0});
  else if(n==="july4"||n==="newyear"){burst(W*.3,H*.35,["#ff4d4d","#ffffff","#5fa8ff","#ffd700"],light?24:46,4);setTimeout(function(){burst(W*.7,H*.3,["#ffd700","#ff4dd2","#7dff8a","#ffffff"],light?24:46,4)},350)}
  else if(n==="valentines")burst(W/2,H/2,["#ff5c8a","#ff8fb8","#ff2e63"],light?12:24,3.5,"heart");
  else if(n==="stpatricks")fx.push({k:"rainbow",t:0});
  else if(n==="thanksgiving")for(var i=0;i<(light?10:20);i++)fx.push({k:"gust",x:-20-rnd(0,120),y:rnd(40,H-60),vx:rnd(5,9),vy:rnd(-1,1),a:0,c:["#d9531e","#e8902a","#b5341c","#c9a227"][i%4],s:rnd(6,10),life:1});
  else if(n==="easter")fx.push({k:"egg",x:-30,y:H-70,t:0});}
function drawFx(dt){
  for(var i=fx.length-1;i>=0;i--){var f=fx[i];
    if(f.k==="spark"){f.x+=f.vx*dt;f.y+=f.vy*dt;f.vy+=.06*dt;f.life-=.018*dt;ctx.globalAlpha=Math.max(0,f.life);
      if(f.shape==="heart")heart(f.x,f.y,f.s*1.6,f.c);else{ctx.fillStyle=f.c;ctx.fillRect(f.x,f.y,f.s,f.s)}ctx.globalAlpha=1;if(f.life<=0)fx.splice(i,1)}
    else if(f.k==="bigbat"){f.t+=dt;f.x-=7*dt;f.y=H*.55-Math.sin(f.t/16)*H*.28;bat(f.x,f.y,26,f.t*.45,"#0d0614");if(f.x<-80)fx.splice(i,1)}
    else if(f.k==="sleigh"){f.t+=dt;f.x+=5*dt;var y=f.y+Math.sin(f.t/10)*6;ctx.fillStyle="#1a0f08";
      for(var d=0;d<3;d++){var dx=f.x+90+d*26,dy=y+Math.sin(f.t/5+d)*2;ctx.fillRect(dx,dy,16,6);ctx.fillRect(dx+13,dy-6,3,7);ctx.fillRect(dx+1,dy+6,2,6);ctx.fillRect(dx+12,dy+6,2,6)}
      ctx.fillRect(f.x+8,y-2,56,12);ctx.fillRect(f.x,y+12,70,3);ctx.beginPath();ctx.moveTo(f.x+64,y);ctx.lineTo(f.x+90,y+3);ctx.lineTo(f.x+64,y+4);ctx.fill();
      ctx.fillStyle="#d21f2b";ctx.beginPath();ctx.arc(f.x+150,y+1,2.4,0,6.28);ctx.fill();if(f.x>W+40)fx.splice(i,1)}
    else if(f.k==="rainbow"){f.t+=dt;var al=f.t<30?f.t/30:Math.max(0,1-(f.t-60)/40);ctx.globalAlpha=al*.55;["#ff4d4d","#ff9a3d","#ffe14d","#5fdc5f","#4da6ff","#9b6bd6"].forEach(function(c,k){ctx.strokeStyle=c;ctx.lineWidth=8;ctx.beginPath();ctx.arc(W/2,H+40,H*.75-k*8,Math.PI*1.08,Math.PI*1.92);ctx.stroke()});ctx.globalAlpha=1;if(f.t>100)fx.splice(i,1)}
    else if(f.k==="gust"){f.x+=f.vx*dt;f.y+=f.vy*dt;f.a+=.2*dt;ctx.save();ctx.translate(f.x,f.y);ctx.rotate(f.a);ctx.fillStyle=f.c;ctx.beginPath();ctx.ellipse(0,0,f.s,f.s*.5,0,0,6.28);ctx.fill();ctx.restore();if(f.x>W+30)fx.splice(i,1)}
    else if(f.k==="egg"){f.t+=dt;f.x+=4.5*dt;var ey=f.y-Math.abs(Math.sin(f.t/7))*40;ctx.save();ctx.translate(f.x,ey);ctx.rotate(Math.sin(f.t/7)*.3);
      var g=ctx.createLinearGradient(0,-16,0,16);g.addColorStop(0,"#ffd1e8");g.addColorStop(.5,"#c9f2c7");g.addColorStop(1,"#d9c6ff");ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(0,0,12,16,0,0,6.28);ctx.fill();
      ctx.strokeStyle="#9b6bd6";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(-11,0);ctx.lineTo(-5,-4);ctx.lineTo(0,0);ctx.lineTo(5,-4);ctx.lineTo(11,0);ctx.stroke();ctx.restore();if(f.x>W+30)fx.splice(i,1)}}}

/* ---------- loop ---------- */
function size(){W=stage.offsetWidth||640;H=stage.offsetHeight||480;if(cv.width!==W||cv.height!==H){cv.width=W;cv.height=H}}
function frame(t){if(!running)return;requestAnimationFrame(frame);
  var dt=last?Math.min(3,(t-last)/16.7):1;if(last&&(lite?t-last<62:light&&t-last<30))return;   /* TV boxes: about 15 frames a second, so the video gets the power */last=t;
  ctx.clearRect(0,0,W,H);if(showParts){for(var i=0;i<parts.length;i++){step(parts[i],dt);drawPart(parts[i],t)}decor(t)}drawFx(dt)}
function init(){stage=document.getElementById("stage");if(!stage)return;
  cv=document.createElement("canvas");cv.id="seasonFx";cv.style.cssText="position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:45";
  stage.appendChild(cv);ctx=cv.getContext("2d");size();for(var i=0;i<COUNT;i++)parts.push(spawn(false));
  addEventListener("resize",function(){setTimeout(size,60)});
  document.addEventListener("visibilitychange",function(){running=!document.hidden;if(running){last=0;requestAnimationFrame(frame)}});
  requestAnimationFrame(frame)}
window.KNASSeason={onTune:onTune,name:S.name,particles:function(on){showParts=!!on}};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
