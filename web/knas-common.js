/* KNAS shared helpers: your names, logos and the volume leveler.
   window.KNAS is added to each page by the server from your settings. */
(function(){
"use strict";
var K=window.KNAS=window.KNAS||{};
K.names=K.names||{};K.logos=K.logos||{};K.audio=K.audio||{};
function N(k,d){return K.names[k]||d}
K.name=N;

/* ---------- logos ---------- */
function img(src,css){var i=document.createElement("img");i.src=src;i.alt="";i.style.cssText="display:block;width:100%;height:100%;object-fit:contain;"+(css||"");return i}
function applyLogos(){
  var page=document.documentElement.getAttribute("data-page")||"";
  // weather and break: the square logo top left
  var sq=document.querySelector("#stage header .logo"),src=page==="break"?(K.logos.cable||K.logos.station):K.logos.station;
  if(sq&&src){sq.innerHTML="";sq.appendChild(img(src));sq.style.cssText+="background:none!important;box-shadow:none!important;overflow:visible"}
  // sports: the badge top left
  var sb=document.querySelector(".st-logo");
  if(sb&&K.logos.sports){sb.innerHTML="";var i=img(K.logos.sports,"height:32px;width:auto;max-width:150px");sb.appendChild(i);sb.style.cssText+="background:none!important;box-shadow:none!important;padding:0"}
  // cable box guide: your logo instead of the "KNAS Cable / TV Guide" words
  var g=document.getElementById("gLogo");
  if(g&&K.logos.cable){var t=g.querySelector(".gl1"),t2=g.querySelector(".gl2");if(t)t.style.display="none";if(t2){t2.innerHTML="";t2.appendChild(img(K.logos.cable,"height:96px;width:auto;max-width:224px"));t2.style.cssText+="background:none!important;-webkit-text-fill-color:initial"}}
}

/* ---------- names ---------- */
function applyNames(){
  var g1=document.querySelector("#gLogo .gl1"),g2=document.querySelector("#gLogo .gl2");
  if(g1)g1.textContent=N("cable","KNAS Cable");if(g2&&!K.logos.cable)g2.textContent=N("guide","TV Guide");
  var tt=document.getElementById("topTitle");if(tt&&tt.textContent==="KNAS Sports")tt.textContent=N("sports","KNAS Sports");
  var b=document.querySelector(".st-logo b");if(b){var w=N("sports","KNAS Sports").trim().split(/\s+/);b.textContent=(w.length>1?w[w.length-1]:w[0]).toUpperCase().slice(0,10)}
  var page=document.documentElement.getAttribute("data-page");
  if(page==="tv")document.title=N("cable","KNAS Cable");else if(page==="sports")document.title=N("sports","KNAS Sports");
}

/* ---------- volume leveler ----------
   Everything that makes sound goes through one chain:
   [TV] [music] [radio] [static]  ->  leveler  ->  loudness  ->  limiter  ->  fade  ->  speakers */
var IOS=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
var A={ctx:null,kinds:{},pending:[],ready:false,cfg:K.audio};
var STRENGTH={light:{t:-22,k:24,r:2.5,a:.02,rl:.35,mk:3},medium:{t:-30,k:18,r:5,a:.006,rl:.25,mk:7},strong:{t:-40,k:10,r:12,a:.003,rl:.18,mk:12}};
function db(x){return Math.pow(10,x/20)}
function build(){
  if(A.ctx||IOS)return A.ctx;
  var AC=window.AudioContext||window.webkitAudioContext;if(!AC)return null;
  try{A.ctx=new AC()}catch(e){return null}
  var c=A.ctx,cfg=A.cfg,out=c.destination;
  A.master=c.createGain();A.master.gain.value=A.vol==null?1:A.vol;A.master.connect(out);out=A.master;   /* the viewer's volume / mute */
  A.fade=c.createGain();A.fade.connect(out);out=A.fade;
  if(cfg.limit!==false){var lim=c.createDynamicsCompressor();lim.threshold.value=cfg.ceiling==null?-1:cfg.ceiling;lim.knee.value=0;lim.ratio.value=20;lim.attack.value=.002;lim.release.value=.08;lim.connect(out);out=lim}
  if(cfg.level!==false){var s=STRENGTH[cfg.strength]||STRENGTH.medium,mk=c.createGain();mk.gain.value=db(s.mk+(+cfg.target||0));mk.connect(out);
    var comp=c.createDynamicsCompressor();comp.threshold.value=s.t;comp.knee.value=s.k;comp.ratio.value=s.r;comp.attack.value=s.a;comp.release.value=s.rl;comp.connect(mk);out=comp}
  else if(cfg.target){var tg=c.createGain();tg.gain.value=db(+cfg.target);tg.connect(out);out=tg}
  A.input=out;
  ["tv","music","radio","static"].forEach(function(k){var g=c.createGain();g.gain.value=cfg[k]==null?1:+cfg[k];g.connect(A.input);A.kinds[k]=g});
  function go(){if(c.state==="running"){A.ready=true;flush()}}
  c.onstatechange=go;go();
  var unlock=function(){if(c.state!=="running")c.resume().then(go).catch(function(){})};
  ["keydown","click","touchend","pointerdown"].forEach(function(ev){document.addEventListener(ev,unlock,true)});
  window.addEventListener("message",function(e){if(e.data==="knas-unlock")unlock()});
  return c}
function flush(){A.pending.splice(0).forEach(function(p){connect(p[0],p[1])})}
function connect(el,kind){if(el._knasSrc)return;try{var src=A.ctx.createMediaElementSource(el);src.connect(A.kinds[kind]||A.kinds.tv);el._knasSrc=src;el.volume=1}catch(e){console.warn("leveler:",e)}}
var KA=window.KNASAudio={
  /* send a <video>/<audio> element through the leveler (it plays normally until the page is allowed to use sound) */
  attach:function(el,kind){if(!el)return;var vol=A.cfg[kind]==null?1:+A.cfg[kind];
    if(IOS||!build()){try{el.volume=Math.min(1,vol)}catch(e){}return}
    if(A.ready)connect(el,kind);else{try{el.volume=Math.min(1,vol)}catch(e){}A.pending.push([el,kind])}},
  /* the audio context everything shares (the cable box uses it for the static) */
  context:function(){return build()},
  input:function(kind){build();return A.kinds[kind]||null},
  /* soft fade-in after changing channel */
  fadeIn:function(){if(!A.ctx||!A.fade)return;var ms=A.cfg.fade==null?700:+A.cfg.fade,t=A.ctx.currentTime;if(!ms)return;
    A.fade.gain.cancelScheduledValues(t);A.fade.gain.setValueAtTime(0.0001,t);A.fade.gain.exponentialRampToValueAtTime(1,t+ms/1000)},
  active:function(){return !!(A.ctx&&A.ready)},
  /* the viewer's own volume, 0 to 1 (0 = muted). Affects everything at once. */
  setVolume:function(v){A.vol=Math.max(0,Math.min(1,+v||0));if(A.master)try{A.master.gain.setTargetAtTime(A.vol,A.ctx.currentTime,.03)}catch(e){A.master.gain.value=A.vol}},
  volume:function(){return A.vol==null?1:A.vol}
};

/* ---------- older TV browsers ----------
   Some smart TVs' built-in browsers are a few years old and ignore "gap" spacing in flex layouts.
   There, add the same spacing with margins so nothing squashes together. */
function flexGapFix(){
  try{var t=document.createElement("div");t.style.cssText="display:flex;flex-direction:column;gap:1px;position:absolute;visibility:hidden";
    t.appendChild(document.createElement("div"));t.appendChild(document.createElement("div"));document.body.appendChild(t);
    var ok=t.scrollHeight===1;t.parentNode.removeChild(t);if(ok)return}catch(e){return}
  var out=[];
  [].forEach.call(document.styleSheets,function(sh){var rules;try{rules=sh.cssRules}catch(e){return}
    (function walk(list,wrap){[].forEach.call(list||[],function(r){
      if(r.cssRules&&r.media){walk(r.cssRules,"@media "+r.media.mediaText);return}
      var st=r.style;if(!st||!r.selectorText)return;var g=st.getPropertyValue("gap")||st.getPropertyValue("row-gap");
      if(!g||(st.display||"").indexOf("flex")<0)return;var parts=g.trim().split(/\s+/),col=(st.flexDirection||"").indexOf("column")===0;
      var sel=r.selectorText.split(",").map(function(x){return x.trim()+">*+*"}).join(",");
      var css=sel+"{"+(col?"margin-top:"+parts[0]:"margin-left:"+(parts[1]||parts[0]))+"!important}";
      out.push(wrap?wrap+"{"+css+"}":css)})})(rules)});
  if(out.length){var el=document.createElement("style");el.id="knas-gapfix";el.textContent=out.join("\n");document.head.appendChild(el)}}
function init(){try{applyLogos()}catch(e){}try{applyNames()}catch(e){}try{flexGapFix()}catch(e){}}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
