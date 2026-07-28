# Sethu Ambassador GE Chat — prototype copy (decoded)

Plain-text extraction of `Sethu Ambassador GE Chat.html`. This is the
chat-native design the agent implements; the cockpit file is the earlier
mobile-app design it derives from.

Note the copy is stored as JS string literals with \\uXXXX escapes, so a
naive grep for a typographic apostrophe misses. Unescape before comparing,
and compare CONTIGUOUS literals: many user-facing strings are concatenated
at runtime from several literals plus interpolated names and counts.

```
/* cyrillic-ext */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 400;
font-display: swap;
src: url("8da992b1-cb95-4442-85a7-c6e132a5fefc") format('woff2');
unicode-range: U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F;
}
/* cyrillic */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 400;
font-display: swap;
src: url("19d71aa3-238c-471a-a16d-aa440ceee34f") format('woff2');
unicode-range: U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;
}
/* vietnamese */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 400;
font-display: swap;
src: url("1635af0d-c93d-4e78-a94c-6621f681d0cb") format('woff2');
unicode-range: U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB;
}
/* latin-ext */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 400;
font-display: swap;
src: url("6bae2ea3-8ccc-47b5-8935-2198f5d40c93") format('woff2');
unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
/* latin */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 400;
font-display: swap;
src: url("96f5c942-3bba-4dcd-807c-4d80f216b6bb") format('woff2');
unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
/* cyrillic-ext */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 500;
font-display: swap;
src: url("c13a4a1c-4b6b-4820-8155-68f0e49e4b8e") format('woff2');
unicode-range: U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F;
}
/* cyrillic */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 500;
font-display: swap;
src: url("1867f741-252d-4f6d-a958-0d2135d465a0") format('woff2');
unicode-range: U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;
}
/* vietnamese */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 500;
font-display: swap;
src: url("8ea7054a-a28d-4ec5-bdd4-55ffdb8ebef5") format('woff2');
unicode-range: U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB;
}
/* latin-ext */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 500;
font-display: swap;
src: url("e97f3163-0599-4f72-8305-4ed6135e7d9a") format('woff2');
unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
/* latin */
@font-face {
font-family: 'IBM Plex Mono';
font-style: normal;
font-weight: 500;
font-display: swap;
src: url("b490f20f-93ff-4660-a89e-a6765d1bad1a") format('woff2');
unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
/* latin-ext */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 400;
font-stretch: 100%;
font-display: swap;
src: url("9900e5db-057e-47bb-8f12-c312e8148e71") format('woff2');
unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
/* latin */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 400;
font-stretch: 100%;
font-display: swap;
src: url("e9e6ecc3-1319-4e08-a9a5-41c8d55ee780") format('woff2');
unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
/* latin-ext */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 500;
font-stretch: 100%;
font-display: swap;
src: url("9900e5db-057e-47bb-8f12-c312e8148e71") format('woff2');
unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
/* latin */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 500;
font-stretch: 100%;
font-display: swap;
src: url("e9e6ecc3-1319-4e08-a9a5-41c8d55ee780") format('woff2');
unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
/* latin-ext */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 600;
font-stretch: 100%;
font-display: swap;
src: url("9900e5db-057e-47bb-8f12-c312e8148e71") format('woff2');
unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
/* latin */
@font-face {
font-family: 'Instrument Sans';
font-style: normal;
font-weight: 600;
font-stretch: 100%;
font-display: swap;
src: url("e9e6ecc3-1319-4e08-a9a5-41c8d55ee780") format('woff2');
unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
body{margin:0;background:#EFEBE4;font-family:'Instrument Sans',system-ui,sans-serif;color:#202124}
a{color:#1A73E8;text-decoration:none}a:hover{color:#1557B0}
input::placeholder,textarea::placeholder{color:#BDC1C6}
@keyframes geDot{0%,60%,100%{opacity:.25}30%{opacity:1}}
Campus Ambassador — chat-native in GE
[BUTTON] ↻ restart
☰
CA
Campus Ambassador
Gemini Enterprise · SVEC Tirupati
GE CHROME
{{ m.text }}
{{ m.tag }}
{{ m.text }}
{{ m.card.label }}
{{ m.card.value }}
{{ m.card.pct }}
{{ m.card.note }}
[BUTTON] {{ a.label }}
{{ s.initials }}
{{ s.name }}
{{ s.meta }}
{{ s.msg }}
{{ s.link }}
[BUTTON] Send from my WhatsApp
[BUTTON] Edit
{{ h.label }}
{{ c.text }}
{{ m.foot }}
{{ m.formTitle }}
Angle
{{ a.label }}
Message
[BUTTON] {{ m.formCta }}
{{ m.follow }}
{{ c.label }}
[BUTTON] ↑
Everything here is agent output
No tab bar, no screens, no back button — GE owns the shell. The agent emits A2UI component trees into one transcript, and GE renders them. This is the version that can actually ship on GE today.
{{ tagMark }}
Label each block with its A2UI components
Component budget
{{ b.name }}
{{ b.use }}
Build path
— A2UI rendering in GE needs a self-serve agent registered on the A2A path. Managed ADK agents on Vertex AI Agent Engine don't render A2UI today, so that choice is made at registration, not later.
▶ simulate: {{ phaseLabel }}
class Component extends DCLogic {
state = { turns:[], draft:'', thinking:false, phase:'live', sent:{}, tags:false,
editId:null, drafts:{}, seq:0 };
constructor(props){
super(props);
this.stragglers=[
{id:'pn',initials:'PN',name:'Priya Nandakumar',color:'#CE82FF',context:'ignored 2 campaigns · 11 days'},
{id:'sk',initials:'SK',name:'Suresh Kumar',color:'#1A73E8',context:'ignored 2 campaigns · 9 days'},
{id:'ar',initials:'AR',name:'Anjali Rao',color:'#F9AB00',context:'ignored 2 campaigns · 14 days'},
{id:'vm',initials:'VM',name:'Vikram Mehta',color:'#D93025',context:'never opened a link · 16 days'},
{id:'dg',initials:'DG',name:'Deepa Gowda',color:'#1967D2',context:'ignored 2 campaigns · 8 days'},
{id:'rt',initials:'RT',name:'Rahul Tiwari',color:'#5F6368',context:'ignored 2 campaigns · 12 days'}];
this.roster=[
['Aarti Sharma','activated','via your link · 4 Jul'],
['Bharath Reddy','activated','via campaign · 6 Jul'],
['Chandana M','pending','in campaign cycle'],
['Divya Prakash','activated','via your link · 2 Jul'],
['Eshwar Naidu','pending','ignored 2 campaigns'],
['Farhan Ali','activated','via faculty agent · 8 Jul']];
this.board=[
['Ananya Nair','CSE Sem 5 · A','96.7%','58 / 60','#CE82FF'],
['Farhan Sheikh','ECE Sem 3 · A','94.9%','56 / 59','#1A73E8'],
['You','EEE Sem 3 · B','','','#F9AB00'],
['Divya Tripathi','IT Sem 3 · A','89.5%','51 / 57','#1967D2']];
this.angleDefs=[['Exam panic','internals are Tuesday'],['Placement','final-year framing'],['Plain','no angle']];
}
componentDidMount(){ this.greet(); }
componentWillUnmount(){ clearTimeout(this._t); }
facts(){
const st=this.state, p=st.phase;
const isTarget=p==='target', isComplete=p==='complete';
const pool=isTarget?this.stragglers.slice(4):this.stragglers;
const pending=isComplete?[]:pool.filter(s=>!st.sent[s.id]);
const activated=isComplete?59:(isTarget?54:43);
return {isTarget,isComplete,isLive:p==='live',pending,n:pending.length,activated,
pct:(activated/59*100).toFixed(1)+'%'};
}
milestoneLine(f){
return f.isComplete?'Every student in Sec B is activated — nothing left to unlock.'
:(f.isTarget?'Your 75% milestone is earned. '+(59-f.activated)+' more makes Full House, the 100% badge.'
:(()=>{const need=Math.max(Math.ceil(59*0.75)-f.activated,0);
return need+(need===1?' more activation clears':' more activations clear')+' your 75% milestone.';})());
}
snapshot(){
const f=this.facts();
return {activated:f.activated, pct:f.pct, n:f.n,
note:this.milestoneLine(f)+(f.n?(' '+f.n+(f.n===1?' student needs':' students need')+' a personal message from you.'):''),
board:this.boardRows(f), rewards:this.rewardRows(f), roster:this.rosterRows()};
}
boardRows(f){
const rows=this.board.map(r=>r[0]==='You'
?{name:r[0],pct:f.pct,count:f.activated+' / 59',val:parseFloat(f.pct)}
:{name:r[0],pct:r[2],count:r[3],val:parseFloat(r[2])});
rows.sort((a,b)=>b.val-a.val);
const slots=f.isLive?[1,2,3,19]:[1,2,3,4];
return rows.map((r,i)=>({cells:[
{text:'#'+slots[i],align:'left',family:"'IBM Plex Mono'",weight:'500',color:r.name==='You'?'#1967D2':'#5F6368',size:'12px'},
{text:r.name+(r.name==='You'?' · Sec B':''),align:'left',family:"'Instrument Sans'",weight:r.name==='You'?'600':'400',color:'#202124',size:'12.5px'},
{text:r.pct,align:'right',family:"'IBM Plex Mono'",weight:'500',color:'#1967D2',size:'12px'},
{text:r.count,align:'right',family:"'IBM Plex Mono'",weight:'400',color:'#80868B',size:'11.5px'}],
bg:r.name==='You'?'#E8F0FE':'#fff'}));
}
rewardRows(f){
return [['25%','Starter','earned'],['50%','Half-way','earned'],
['75%','75% Club — tee + certificate',f.isLive?(Math.max(Math.ceil(59*0.75)-f.activated,0)+' more'):'earned'],
['100%','Full House — the 100% badge',f.isComplete?'earned':(59-f.activated)+' more']]
.map(r=>({cells:[
{text:r[0],align:'left',family:"'IBM Plex Mono'",weight:'500',color:'#5F6368',size:'12px'},
{text:r[1],align:'left',family:"'Instrument Sans'",weight:'400',color:'#202124',size:'12.5px'},
{text:r[2],align:'right',family:"'Instrument Sans'",weight:'500',color:r[2]==='earned'?'#1967D2':'#B06000',size:'11.5px'}],
bg:'#fff'}));
}
rosterRows(){
return this.roster.map(r=>({cells:[
{text:r[0],align:'left',family:"'Instrument Sans'",weight:'400',color:'#202124',size:'12.5px'},
{text:r[1],align:'left',family:"'Instrument Sans'",weight:'500',color:r[1]==='activated'?'#1967D2':'#B06000',size:'11.5px'},
{text:r[2],align:'right',family:"'Instrument Sans'",weight:'400',color:'#80868B',size:'11px'}],bg:'#fff'}));
}
push(turn){
const snap=turn.who==='a'?this.snapshot():null;
this.setState(s=>({turns:[...s.turns,{id:++s.seq,snap,...turn}],seq:s.seq+1}));
}
greet(){
const f=this.facts();
this.push({who:'a',kind:'text',
text:'Hi Sneha — I look after EEE Sem 3, Sec B with you.\n\nRight now '+f.activated+' of your 59 classmates are activated ('+f.pct+'), from Google\u2019s certified reporting. '+this.milestoneLine(f),
tag:'Text', follow:'Ask me anything about your section, or pick a suggestion below.'});
}
reply(q){
const t=q.toLowerCase(), f=this.facts();
if(t.includes('nudge')||t.includes('message')||t.includes('who should')){
if(!f.n) return [{kind:'text',tag:'Text',
text:f.isComplete?'Nobody left to chase — all 59 are activated.'
:'Nobody is waiting on you. Everyone still pending is inside Sethu\u2019s campaign cycle; they escalate to you only after ignoring two.'}];
return [{kind:'text',tag:'Text',
text:f.n+(f.n===1?' student has':' students have')+' ignored two campaigns — a broadcast won\u2019t move them. I\u2019ve drafted one message each, in the angle that converts best this week.'},
{kind:'list',tag:'Card · Button ×'+f.n,ids:f.pending.map(s=>s.id),
follow:'You send from your own WhatsApp — I never send as you. Your link carries your credit.'}];
}
if(t.includes('rank')||t.includes('leader'))
return [{kind:'text',tag:'Text',
text:'You\u2019re ranked on % of your section activated — sections under 30 students are pooled. Sec B is at '+f.activated+' of 59 ('+f.pct+'). '+this.milestoneLine(f)},
{kind:'board',tag:'Table',follow:'% and count are always shown together — that\u2019s a fairness rule, not a display choice.'}];
if(t.includes('reward')||t.includes('badge')||t.includes('credential')||t.includes('unlock')||t.includes('next'))
return [{kind:'text',tag:'Text',text:this.milestoneLine(f)},
{kind:'rewards',tag:'Table',follow:'Your credential is yours regardless of rank. Rewards are fulfilled at close-out, and follow section outcomes — never effort.'}];
if(t.includes('cohort')||t.includes('list')||t.includes('roster')||t.includes('who is'))
return [{kind:'text',tag:'Text',text:'EEE Sem 3, Sec B — 59 students from the college roster, '+f.activated+' activated.'},
{kind:'roster',tag:'Table',follow:'Ask me to filter it — "show only pending" or "who activated this week".'}];
if(t.includes('how many')||t.includes('progress')||t.includes('pace')||t.includes('left')||t.includes('stand'))
return [{kind:'cohort',tag:'Card · ProgressBar · Button ×2'}];
return [{kind:'text',tag:'Text',
text:'I only know your section. Try "who should I message?", "where do I stand?", "how is my rank calculated?" or "what unlocks next?"'}];
}
ask(text){
const q=(text||'').trim();
if(!q) return;
clearTimeout(this._t);
this.push({who:'u',text:q});
this.setState({draft:'',thinking:true});
this._t=setTimeout(()=>{
this.setState({thinking:false});
this.reply(q).forEach(r=>this.push({who:'a',...r}));
},800);
}
sendOne(s){
if(this.state.sent[s.id]) return;
this.setState(x=>({sent:{...x.sent,[s.id]:true},editId:null}));
this.push({who:'a',kind:'text',tag:'Text',
text:'Opened WhatsApp with the message for '+s.name.split(' ')[0]+'. Once that sign-in lands, the activation is credited to you — usually within the hour.'});
}
openEdit(s){
this.setState(x=>({editId:s.id,
drafts:{...x.drafts,[s.id]:x.drafts[s.id]||{angle:'Exam panic',text:this.msgFor(s)}}}));
this.push({who:'a',kind:'form',tag:'Form · ChoicePicker · TextField · Button',who2:s.id,name:s.name});
}
msgFor(s,angle){
const first=s.name.split(' ')[0];
const d=(this.state.drafts||{})[s.id];
const a=angle||(d&&d.angle)||'Exam panic';
if(!angle&&d&&d.text) return d.text;
if(a==='Placement') return 'Hey '+first+' — the placement agent has the companies that actually recruit here, with real interview questions. Two minutes to set up, college login:';
if(a==='Plain') return 'Hey '+first+' — your college study agents are ready. One tap, college login, nothing to install:';
return 'Hey '+first+' — internals Tuesday. The Circuits agent makes practice papers from ma\u2019am\u2019s actual notes. One tap, college login:';
}
renderVals(){
const st=this.state, f=this.facts();
const turns=st.turns.map(m=>{
const base={key:m.id, isUser:m.who==='u', isAgent:m.who==='a', text:m.text||'',
justify:m.who==='u'?'end':'start', showTag:st.tags&&m.who==='a'&&!!m.tag, tag:m.tag||'',
isText:m.kind==='text', isCohort:m.kind==='cohort', isList:m.kind==='list',
isTable:m.kind==='board'||m.kind==='rewards'||m.kind==='roster', isForm:m.kind==='form',
hasFollow:!!m.follow, follow:m.follow||'', hasFoot:false, foot:'',
card:{label:'',value:'',pct:'0%',note:'',actions:[]}, cols:'1fr', head:[], rows:[], items:[], angles:[],
formTitle:'', formWho:'', formText:'', setFormText:()=>{}, submit:()=>{},
formLocked:false, formTextColor:'#202124', formTextBg:'#fff', formCta:'',
formBtnBg:'#1A73E8', formBtnFg:'#fff', formBtnCursor:'pointer'};
const sn=m.snap||{};
if(m.kind==='cohort'){
base.card={label:'EEE SEM 3 · SEC B — CERTIFIED',
value:sn.activated+' / 59', pct:sn.pct, note:sn.note,
actions:[{label:sn.n?('Show the '+sn.n+' who need me'):'Show my cohort',
go:()=>this.ask(sn.n?'who should I message?':'show my cohort')},
{label:'How is my rank calculated?',go:()=>this.ask('how is my rank calculated?')}]};
}
if(m.kind==='list') base.items=(m.ids||[]).map(id=>this.stragglers.find(x=>x.id===id)).filter(Boolean).map(s=>({
initials:s.initials,name:s.name,meta:st.sent[s.id]?'message opened in WhatsApp':s.context,
metaColor:st.sent[s.id]?'#1967D2':'#B06000',color:s.color,
border:st.sent[s.id]?'#D2E3FC':'#DADCE0', bg:st.sent[s.id]?'#F7FAFE':'#fff',
pending:!st.sent[s.id], msg:this.msgFor(s), link:'sethu.app/go/'+s.id+'8x2',
send:()=>this.sendOne(s), edit:()=>this.openEdit(s)}));
if(m.kind==='board'){ base.cols='40px 1fr 62px 62px';
base.head=[{label:'Rank',align:'left'},{label:'Ambassador',align:'left'},{label:'%',align:'right'},{label:'Count',align:'right'}];
base.rows=sn.board||[]; base.hasFoot=true; base.foot='178 qualifying sections · under-30 pooled'; }
if(m.kind==='rewards'){ base.cols='44px 1fr 70px';
base.head=[{label:'At',align:'left'},{label:'Reward',align:'left'},{label:'Status',align:'right'}];
base.rows=sn.rewards||[]; }
if(m.kind==='roster'){ base.cols='1fr 74px 96px';
base.head=[{label:'Student',align:'left'},{label:'Status',align:'left'},{label:'How',align:'right'}];
base.rows=sn.roster||[]; base.hasFoot=true; base.foot='Showing 6 of 59'; }
if(m.kind==='form'){
const s=this.stragglers.find(x=>x.id===m.who2)||{name:'them',id:'x'};
base.formTitle='Edit before sending — '+s.name;
base.formWho=s.name.split(' ')[0];
base.formId=s.id;
const done=!!st.sent[s.id];
base.formTitle=done?('Sent — '+s.name):('Edit before sending — '+s.name);
base.formLocked=done;
base.formTextColor=done?'#5F6368':'#202124';
base.formTextBg=done?'#F8F9FA':'#fff';
base.formCta=done?('Sent to '+s.name.split(' ')[0]+' \u2713'):('Send to '+s.name.split(' ')[0]);
base.formBtnBg=done?'#F1F3F4':'#1A73E8';
base.formBtnFg=done?'#5F6368':'#fff';
base.formBtnCursor=done?'default':'pointer';
base.formText=((st.drafts||{})[s.id]||{}).text||'';
base.setFormText=done?(()=>{}):(e=>{ const v=e.target.value;
this.setState(x=>({drafts:{...x.drafts,[s.id]:{...(x.drafts[s.id]||{}),text:v}}})); });
base.angles=this.angleDefs.map(a=>{
const cur=((st.drafts||{})[s.id]||{}).angle||'Exam panic';
const on=cur===a[0];
return {label:a[0],
border:on?(done?'#BDC1C6':'#1A73E8'):'#DADCE0',
bg:on?(done?'#F1F3F4':'#E8F0FE'):'#fff',
color:on?(done?'#5F6368':'#1557B0'):'#5F6368',
cursor:done?'default':'pointer', opacity:done?'.7':'1',
pick:done?(()=>{}):(()=>this.setState(x=>({drafts:{...x.drafts,[s.id]:{angle:a[0],text:this.msgFor(s,a[0])}}})))};
});
base.submit=()=>this.sendOne(s);
}
return base;
});
const last=[...st.turns].reverse().find(m=>m.who==='a')||{};
const chipSet=last.kind==='list'?['Where do I stand?','What unlocks next?','Show my cohort']
:last.kind==='board'?['Who should I message?','What unlocks next?']
:last.kind==='rewards'?['Who should I message?','Where do I stand?']
:['Who should I message?','Where do I stand?','How is my rank calculated?','What unlocks next?'];
return {
turns, thinking:st.thinking,
draft:st.draft, setDraft:e=>this.setState({draft:e.target.value}),
onKey:e=>{ if(e.key==='Enter') this.ask(this.state.draft); },
send:()=>this.ask(st.draft),
chips:chipSet.map(c=>({label:c,pick:()=>this.ask(c)})),
restart:()=>{ clearTimeout(this._t);
this.setState({turns:[],sent:{},drafts:{},draft:'',thinking:false,editId:null,seq:0},()=>this.greet()); },
tags:st.tags, toggleTags:()=>this.setState({tags:!st.tags}),
tagBorder:st.tags?'#1A73E8':'#DADCE0', tagBox:st.tags?'#1A73E8':'#fff', tagMark:st.tags?'✓':'',
budget:[['Text','prose answers, confirmations'],['Card','the cohort summary, each straggler'],
['Table','leaderboard, roster, rewards'],['Button','send, edit, follow-up actions'],
['ChoicePicker','the angle switch in the edit form'],['TextField','the editable message body'],
['ProgressBar','activation against the section']].map(b=>({name:b[0],use:b[1]})),
phaseLabel:f.isLive?'75% milestone hit':(f.isTarget?'100%':'back to live'),
cyclePhase:()=>this.setState({phase:f.isLive?'target':(f.isTarget?'complete':'live')})
};
}
}
```
