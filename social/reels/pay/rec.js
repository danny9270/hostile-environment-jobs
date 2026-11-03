const { chromium } = require('playwright');const {spawn}=require('child_process');
const [,,url,outp,durA]=process.argv;const fps=30,dur=+durA;
(async()=>{
 const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
 await p.goto(url,{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(500);
 const ff=spawn('ffmpeg',['-y','-f','image2pipe','-framerate',String(fps),'-i','-','-f','lavfi','-i','anullsrc=r=44100:cl=stereo','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-crf','20','-preset','medium','-c:a','aac','-movflags','+faststart',outp],{stdio:['pipe','ignore','inherit']});
 const N=Math.round(fps*dur);
 for(let i=0;i<N;i++){await p.evaluate(t=>render(t),i/fps);const buf=await p.screenshot({type:'jpeg',quality:92});if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r));}
 ff.stdin.end();await new Promise(r=>ff.on('close',r));await b.close();
})();
