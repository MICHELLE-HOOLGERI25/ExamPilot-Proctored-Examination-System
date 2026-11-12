import { FormEvent, useEffect, useState } from "react";
import { Activity, ArrowRight, BookOpen, BrainCircuit, CheckCircle2, Clock3, FileText, GraduationCap, LayoutDashboard, LogOut, Plus, RefreshCw, ShieldCheck, Sparkles, Trophy, Users } from "lucide-react";
import "./App.css";

const API=(import.meta as any).env?.VITE_API_BASE_URL||"http://127.0.0.1:8000";
type User={email:string;name:string;role:"student"|"teacher";roll_number?:number|null;usn?:string|null;division?:string|null};
type Exam={session_id:string;status?:string;total_questions?:number;answered_questions?:number;questions?:any[];student_name?:string;student_roll_number?:number};
async function req(path:string,token?:string,init:RequestInit={}){const h:any={"Content-Type":"application/json",...(init.headers||{})};if(token)h.Authorization=`Bearer ${token}`;const r=await fetch(API+path,{...init,headers:h});const t=await r.text();let d:any={};try{d=t?JSON.parse(t):{}}catch{d={detail:t}}if(!r.ok){const x=d.detail;throw Error(typeof x==="string"?x:Array.isArray(x)?x.map((v:any)=>v.msg).join(", "):x?JSON.stringify(x):`HTTP ${r.status}`)}return d}
const qid=(q:any,i:number)=>String(q.question_id||q.id||`q${i+1}`);
export default function App(){
const [token,setToken]=useState(localStorage.getItem("oce_token")||""),[user,setUser]=useState<User|null>(()=>{try{return JSON.parse(localStorage.getItem("oce_user")||"null")}catch{return null}});
const [mode,setMode]=useState<"login"|"register">("login"),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
const [view,setView]=useState<"home"|"create"|"exam"|"result">("home"),[exams,setExams]=useState<Exam[]>([]),[active,setActive]=useState<Exam|null>(null),[answers,setAnswers]=useState<Record<string,string>>({}),[result,setResult]=useState<any>(null);
const [teacherResults,setTeacherResults]=useState<any[]>([]);
const [a,setA]=useState({email:"",password:"",name:"",role:"student" as "student"|"teacher",roll:"101",usn:"TEST101",division:"A"});
const [f,setF]=useState({
  division:"A",
  subject:"DBMS",
  topic:"SQL",
  difficulty:"easy",
  normal:3,
  scenario:1,
  coding:1,
  count:5
});
const teacher=user?.role==="teacher";
const fail=(e:any)=>setMessage(`⚠ ${e.message||e}`);
async function load(){
  if(!token||!user)return;
  const d=await req(teacher?"/api/teacher/exams":"/api/student/exams",token);
  setExams(Array.isArray(d.exams)?d.exams:[]);
  if(teacher){
    try{
      const r=await req("/api/teacher/results",token);
      setTeacherResults(Array.isArray(r.results)?r.results:[]);
    }catch{
      setTeacherResults([]);
    }
  }
}
useEffect(() => {
  if (!token) return;

  let cancelled = false;

  async function initialise() {
    // Step 1: Validate the login separately.
    let current: User;

    try {
      current = await req("/api/auth/me", token);
    } catch (e: any) {
      if (cancelled) return;

      // Clear the login only if authentication really failed.
      const error = String(e.message || e);

      if (
        error.includes("401") ||
        error.toLowerCase().includes("invalid or expired login session") ||
        error.toLowerCase().includes("invalid authentication credentials")
      ) {
        localStorage.removeItem("oce_token");
        localStorage.removeItem("oce_user");
        setToken("");
        setUser(null);
        setExams([]);
        setMessage("Your login expired. Please sign in again.");
      } else {
        setMessage(`Could not verify login: ${error}`);
      }

      return;
    }

    if (cancelled) return;

    setUser(current);
    localStorage.setItem("oce_user", JSON.stringify(current));

    // Step 2: Load the appropriate dashboard separately.
    try {
      const path =
        current.role === "teacher"
          ? "/api/teacher/exams"
          : "/api/student/exams";

      const data = await req(path, token);

      if (!cancelled) {
        setExams(Array.isArray(data.exams) ? data.exams : []);
        setMessage("");
        if(current.role==="teacher"){
          try{
            const r=await req("/api/teacher/results",token);
            if(!cancelled)setTeacherResults(Array.isArray(r.results)?r.results:[]);
          }catch{
            if(!cancelled)setTeacherResults([]);
          }
        }
      }
    } catch (e: any) {
      if (!cancelled) {
        // Keep the valid login. Show the actual API error instead.
        setExams([]);
        setMessage(
          `Login succeeded, but exams could not be loaded: ${
            e.message || e
          }`
        );
      }
    }
  }

  initialise();

  return () => {
    cancelled = true;
  };
}, [token]);
async function auth(e:FormEvent){e.preventDefault();setBusy(true);setMessage("");try{if(mode==="register"){await req("/api/auth/register",undefined,{method:"POST",body:JSON.stringify({email:a.email,password:a.password,name:a.name,roll_number:Number(a.roll),usn:a.usn,division:a.division,role:a.role})});setMode("login");setMessage("Account created. Sign in now.")}else{const d=await req("/api/auth/login",undefined,{method:"POST",body:JSON.stringify({email:a.email,password:a.password})});setToken(d.access_token);setUser(d.user);localStorage.setItem("oce_token",d.access_token);localStorage.setItem("oce_user",JSON.stringify(d.user));setMessage(`Signed in as ${d.user.role}.`)}}catch(e:any){fail(e)}finally{setBusy(false)}}
function logout(){localStorage.removeItem("oce_token");localStorage.removeItem("oce_user");setToken("");setUser(null);setExams([]);setTeacherResults([]);setView("home")}
async function create(e:FormEvent){
  e.preventDefault();

  if(f.normal + f.scenario + f.coding !== f.count){
    setMessage("⚠ Question mix must equal total questions.");
    return;
  }

  setBusy(true);
  setMessage("");

  try{
    /*
      The existing backend ExamRequest requires Student.
      These placeholder identity values are ONLY generation context.
      api.py now assigns the generated examination by division.
    */
    const payload = {
      student:{
        name:`Division ${f.division}`,
        roll_number:1,
        usn:`DIV-${f.division}`,
        division:f.division.trim()
      },
      subject:f.subject,
      topic:f.topic,
      difficulty:f.difficulty,
      number_of_questions:Number(f.count),
      question_mix:{
        normal_mcq:Number(f.normal),
        scenario_mcq:Number(f.scenario),
        coding:Number(f.coding)
      },
      exam_mode:"practice"
    };

    const d=await req(
      "/api/exams",
      token,
      {
        method:"POST",
        body:JSON.stringify(payload)
      }
    );

    setMessage(
      `✓ Exam generated successfully for Division ${f.division}.`
    );

    setView("home");

    const refreshed=await req(
      "/api/teacher/exams",
      token
    );

    setExams(
      Array.isArray(refreshed.exams)
        ? refreshed.exams
        : []
    );

  }catch(e:any){
    fail(e);
  }finally{
    setBusy(false);
  }
}
async function openExam(x: Exam) {
  setBusy(true);
  setMessage("");

  try {
    const d = await req(
      `/api/exams/${encodeURIComponent(x.session_id)}`,
      token
    );

    if (!d.session_id) {
      throw new Error(
        "Backend did not return a student exam session."
      );
    }

    setActive(d);
    setAnswers({});
    setResult(null);
    setView("exam");

  } catch (e: any) {
    fail(e);
  } finally {
    setBusy(false);
  }
}
async function submit(){if(!active)return;setBusy(true);try{for(let i=0;i<(active.questions||[]).length;i++){const id=qid(active.questions[i],i);if(answers[id]!==undefined)await req(`/api/exams/${active.session_id}/answers`,token,{method:"POST",body:JSON.stringify({question_id:id,answer:answers[id]})})}const d=await req(`/api/exams/${active.session_id}/submit`,token,{method:"POST",body:"{}"});setResult(d);setView("result");setMessage("Submission sent to evaluation.");await load()}catch(e:any){fail(e)}finally{setBusy(false)}}
if(!token||!user)return <div className="auth"><section className="hero"><div className="brand"><span className="logo"><BrainCircuit/></span> Exam<span>Pilot</span></div><div className="hero-copy"><small>✦ AGENTIC EXAMINATION PLATFORM</small><h1>Assess knowledge.<br/><em>Not just answers.</em></h1><p>Validated questions, secure exam sessions, and automated evaluation in one focused workspace.</p><div className="features"><p><ShieldCheck/><span><b>Secure by design</b><small>Role-aware access and protected attempts</small></span></p><p><BrainCircuit/><span><b>Agent-powered evaluation</b><small>Structured scoring and feedback</small></span></p><p><Activity/><span><b>Live exam workflow</b><small>From creation to final result</small></span></p></div></div><small className="hero-foot">ONLINE COURSE EXAMINATION SYSTEM · FRIEND 4</small></section><section className="auth-main"><div className="auth-switch">{mode==="login"?"New here?":"Already registered?"} <button onClick={()=>setMode(mode==="login"?"register":"login")}>{mode==="login"?"Create account":"Sign in"}</button></div><div className="auth-card"><div className="auth-logo"><GraduationCap/></div><small>{mode==="login"?"YOUR WORKSPACE AWAITS":"GET STARTED"}</small><h2>{mode==="login"?"Welcome back":"Create your account"}</h2><p>{mode==="login"?"Sign in to continue to your workspace.":"Choose a role for your demo account."}</p>{message&&<div className="message">{message}</div>}<form onSubmit={auth} className="stack">{mode==="register"&&<><label>Full name<input required value={a.name} onChange={e=>setA({...a,name:e.target.value})}/></label><label>Role<select value={a.role} onChange={e=>setA({...a,role:e.target.value as any})}><option value="student">Student</option><option value="teacher">Teacher</option></select></label>{a.role==="student"&&<div className="two"><label>Roll number<input required type="number" value={a.roll} onChange={e=>setA({...a,roll:e.target.value})}/></label><label>Division<input required value={a.division} onChange={e=>setA({...a,division:e.target.value})}/></label><label className="wide">USN<input required value={a.usn} onChange={e=>setA({...a,usn:e.target.value})}/></label></div>}</>}<label>Email<input required type="email" value={a.email} onChange={e=>setA({...a,email:e.target.value})}/></label><label>Password<input required type="password" minLength={8} value={a.password} onChange={e=>setA({...a,password:e.target.value})}/></label><button className="primary full" disabled={busy}>{busy?"Please wait…":mode==="login"?"Sign in securely":"Create account"} <ArrowRight size={16}/></button></form><small className="footnote"><ShieldCheck size={14}/> Credentials are handled by your backend.</small></div><small className="api-label">API service · {API}</small></section></div>;
return <div className="layout"><aside className="sidebar"><div className="brand"><span className="logo"><BrainCircuit/></span> Exam<span>Pilot</span></div><small className="side-label">WORKSPACE</small><button className={view==="home"?"nav active":"nav"} onClick={()=>setView("home")}><LayoutDashboard size={18}/> Overview</button>{teacher&&<button className={view==="create"?"nav active":"nav"} onClick={()=>setView("create")}><Plus size={18}/> Create exam</button>}<div className="side-bottom"><div className="online">● API connected</div><div className="profile"><div className="avatar">{user.name[0]}</div><span><b>{user.name}</b><small>{user.role}{user.division?` · Div ${user.division}`:""}</small></span><button className="icon" onClick={logout} title="Log out"><LogOut size={16}/></button></div></div></aside><main className="main"><header className="topbar"><div><small>WORKSPACE / {view.toUpperCase()}</small><h1>{view==="create"?"Create an examination":view==="exam"?"Exam in progress":view==="result"?"Evaluation results":`Good to see you, ${user.name.split(" ")[0]}`}</h1></div><span className="role">{teacher?<Users size={14}/>:<GraduationCap size={14}/>} {user.role}</span></header>{message&&<div className="message">{message}<button onClick={()=>setMessage("")}>×</button></div>}
{view==="home"&&<><section className="banner"><div><small>✦ YOUR EXAMINATION HUB</small><h2>{teacher?"Design a better assessment.":"Make every attempt count."}</h2><p>{teacher?"Create validated exams and track their evaluation lifecycle.":"Find assigned exams, submit answers, and review results."}</p>{teacher&&<button className="white-btn" onClick={()=>setView("create")}>Create new exam <ArrowRight size={16}/></button>}</div><div className="banner-icon"><BrainCircuit size={56}/><span>✓ Validated</span></div></section><div className="section-head"><div><h2>{teacher?"Exam activity":"Your assigned exams"}</h2><p>{teacher?"Sessions created in this demo.":"Exams assigned to your student identity."}</p></div><button className="secondary" onClick={()=>load().catch(fail)}><RefreshCw size={15}/> Refresh</button></div><div className="stats"><div><FileText/><small>{teacher?"Exams created":"Assigned exams"}</small><b>{exams.length}</b></div><div><Clock3/><small>In progress</small><b>{exams.filter(x=>String(x.status).includes("progress")).length}</b></div><div><Trophy/><small>Completed</small><b>{exams.filter(x=>/submitted|completed|evaluated/i.test(x.status||"")).length}</b></div></div>{!exams.length?<div className="empty"><BookOpen size={28}/><h3>{teacher?"No exams created yet":"No exams assigned yet"}</h3><p>{teacher?"Create one exam for the target division.":"Your teacher's exam will appear here once assigned."}</p>{teacher&&<button className="primary" onClick={()=>setView("create")}>Create first exam <ArrowRight size={16}/></button>}</div>:<div className="cards">{exams.map((x,i)=><article className="exam-card" key={x.session_id}><div className="exam-top"><BookOpen/><span>{(x.status||"ready").replaceAll("_"," ")}</span></div><small>SESSION {String(i+1).padStart(2,"0")}</small><h3>{x.questions?.[0]?.subject||"Course assessment"}</h3><p>{teacher?`Assigned to Division ${(x as any).division||(x as any).target_division||"A"}`:"Complete this assessment and submit for evaluation."}</p><div className="meta"><span><Clock3 size={14}/> {x.answered_questions||0} answered</span><span>{x.total_questions||x.questions?.length||0} questions</span></div>{!teacher&&<button className="link-btn" onClick={()=>openExam(x)} disabled={busy||/submitted|completed|evaluated|locked/i.test(x.status||"")}>{/submitted|completed|evaluated|locked/i.test(x.status||"")?"Exam submitted":"Attend exam"} <ArrowRight size={16}/></button>}</article>)}</div>}</>}
{view==="home"&&teacher&&<section className="panel" style={{marginTop:28}}>
<div className="section-head">
  <div>
    <h2>Student results</h2>
    <p>Results grouped division-wise and separately for each exam.</p>
  </div>
  <button className="secondary" onClick={()=>load().catch(fail)}>
    <RefreshCw size={15}/> Refresh results
  </button>
</div>

{teacherResults.length===0
  ? <div className="empty">
      <Trophy size={28}/>
      <h3>No student submissions yet</h3>
      <p>Results will appear here after a student submits an assigned exam.</p>
    </div>
  : (()=>{
      const divisions=Array.from(
        new Set(teacherResults.map((r:any)=>String(r.division||"Unassigned")))
      ).sort();

      return <div style={{display:"grid",gap:28}}>
        {divisions.map((division:string)=>{
          const divisionRows=teacherResults.filter(
            (r:any)=>String(r.division||"Unassigned")===division
          );

          const examGroups=new Map<string,any[]>();
          divisionRows.forEach((r:any)=>{
            const key=String(
              r.assignment_id ||
              `${r.subject||"Exam"}|${r.topic||""}|${r.total_marks||""}`
            );
            if(!examGroups.has(key))examGroups.set(key,[]);
            examGroups.get(key)!.push(r);
          });

          return <section key={division} style={{
            border:"1px solid #e8ebf4",
            borderRadius:18,
            padding:20,
            background:"#fafbff"
          }}>
            <div style={{marginBottom:18}}>
              <small style={{textTransform:"uppercase",letterSpacing:".08em"}}>
                Division
              </small>
              <h2 style={{margin:"4px 0 0"}}>Division {division}</h2>
            </div>

            <div style={{display:"grid",gap:20}}>
              {Array.from(examGroups.entries()).map(([examKey,rows]:[string,any[]])=>{
                const first=rows[0]||{};
                const assignmentId=first.assignment_id;
                const examIndex=assignmentId
                  ? exams.findIndex((x:any)=>x.session_id===assignmentId)
                  : -1;
                const sessionLabel=examIndex>=0
                  ? `Session ${String(examIndex+1).padStart(2,"0")}`
                  : "Exam";

                return <div key={examKey} style={{
                  background:"#fff",
                  border:"1px solid #e8ebf4",
                  borderRadius:16,
                  padding:18
                }}>
                  <div style={{
                    display:"flex",
                    justifyContent:"space-between",
                    gap:16,
                    alignItems:"center",
                    flexWrap:"wrap",
                    marginBottom:14
                  }}>
                    <div>
                      <small style={{textTransform:"uppercase",letterSpacing:".08em"}}>
                        {sessionLabel}
                      </small>
                      <h3 style={{margin:"4px 0 0"}}>
                        {first.subject||"Exam"}
                        {first.topic?` · ${first.topic}`:""}
                      </h3>
                    </div>
                    <span className="pill">{rows.length} submission{rows.length===1?"":"s"}</span>
                  </div>

                  <div style={{overflowX:"auto"}}>
                    <table style={{width:"100%",borderCollapse:"collapse",minWidth:650}}>
                      <thead>
                        <tr>
                          <th style={{textAlign:"left",padding:12}}>Student</th>
                          <th style={{textAlign:"left",padding:12}}>USN</th>
                          <th style={{textAlign:"left",padding:12}}>Marks</th>
                          <th style={{textAlign:"left",padding:12}}>Percentage</th>
                          <th style={{textAlign:"left",padding:12}}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r:any,i:number)=>
                          <tr key={r.session_id||i} style={{borderTop:"1px solid #e8ebf4"}}>
                            <td style={{padding:12}}>{r.student_name||r.name||"Student"}</td>
                            <td style={{padding:12}}>{r.student_usn||r.usn||"—"}</td>
                            <td style={{padding:12}}>
                              <b>{r.marks??r.marks_awarded??0} / {r.total_marks??0}</b>
                            </td>
                            <td style={{padding:12}}><b>{r.percentage??0}%</b></td>
                            <td style={{padding:12}}>{r.status||"Completed"}</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              })}
            </div>
          </section>
        })}
      </div>
    })()
}
</section>}
{view==="create"&&!teacher&&<section className="panel"><h2>Access restricted</h2><p>Only teacher accounts can create exams.</p><button className="primary" onClick={()=>setView("home")}>Back to student dashboard</button></section>}
{view==="create"&&teacher&&<section className="panel"><h2>Exam configuration</h2><p>Define requirements and target division.</p><form onSubmit={create} className="exam-form"><h3>01 · Target division</h3><div className="grid three"><label>Division<input required value={f.division} onChange={e=>setF({...f,division:e.target.value})}/></label></div><h3>02 · Assessment details</h3><div className="grid three"><label>Subject<select value={f.subject} onChange={e=>setF({...f,subject:e.target.value})}><option>DBMS</option><option>OOPS</option></select></label><label>Topic<input required value={f.topic} onChange={e=>setF({...f,topic:e.target.value})}/></label><label>Difficulty<select value={f.difficulty} onChange={e=>setF({...f,difficulty:e.target.value})}><option>easy</option><option>medium</option><option>hard</option></select></label></div><h3>03 · Question mix</h3><div className="mix">{[["Normal MCQ","normal"],["Scenario MCQ","scenario"],["Coding / SQL","coding"],["Total questions","count"]].map(([label,key])=><label key={key}>{label}<input type="number" min={key==="count"?1:0} value={(f as any)[key]} onChange={e=>setF({...f,[key]:Number(e.target.value)})}/></label>)}</div><div className="form-end"><span><b>{f.normal+f.scenario+f.coding} questions selected</b><small>Question mix must equal total.</small></span><button className="primary" disabled={busy||f.normal+f.scenario+f.coding!==f.count}>{busy?"Generating…":"Generate exam"} <Sparkles size={16}/></button></div></form></section>}
{view==="exam"&&active&&<section className="panel"><h2>Assessment questions</h2><p>Answers are submitted to the backend for evaluation.</p>{(active.questions||[]).map((q,i)=>{const id=qid(q,i),opts=Array.isArray(q.options)?q.options.map((v:any,j)=>[String.fromCharCode(65+j),String(v)]):Object.entries(q.options||{});return <article className="question" key={id}><small>QUESTION {i+1} · {q.question_type||"MCQ"}</small><h3>{q.question||q.text||"Question text unavailable."}</h3>{opts.length?<div className="options">{opts.map(([k,v]:any)=><label key={k} className={answers[id]===k?"chosen":""}><input type="radio" name={id} checked={answers[id]===k} onChange={()=>setAnswers({...answers,[id]:k})}/><b>{k}</b>{v}</label>)}</div>:<label>Your answer<textarea rows={4} value={answers[id]||""} onChange={e=>setAnswers({...answers,[id]:e.target.value})}/></label>}</article>})}<button className="primary" disabled={busy} onClick={submit}>{busy?"Submitting…":"Submit for evaluation"} <ArrowRight size={16}/></button></section>}
{view==="result"&&result&&(()=>{const payload=result?.result||result?.evaluation_results||result;const rows=Array.isArray(payload?.results)?payload.results:Array.isArray(payload)?payload:[];const obtained=rows.reduce((s:number,r:any)=>s+Number(r.marks_awarded||0),0);const total=rows.reduce((s:number,r:any)=>s+Number(r.total_marks||0),0);const percentage=total>0?Math.round((obtained/total)*100):0;return <section className="panel"><div className="empty"><Trophy size={34}/><h2>Thank you!</h2><p>Your examination has been submitted and evaluated successfully.</p>{total>0&&<div className="stats" style={{width:"100%",marginTop:20}}><div><Trophy/><small>Marks</small><b>{obtained} / {total}</b></div><div><CheckCircle2/><small>Percentage</small><b>{percentage}%</b></div><div><ShieldCheck/><small>Status</small><b>Completed</b></div></div>}<button className="primary" onClick={()=>{setView("home");setActive(null);setResult(null);setAnswers({});load().catch(fail)}}>Back to overview</button></div></section>})()}
<footer>ExamPilot · Online Course Examination System <span>Connected to {API}</span></footer></main></div>
}
