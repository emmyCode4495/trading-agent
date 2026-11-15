import { useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { supabase } from '../lib/supabase'
export function Settings(){
 const {token,user,setAuth,logout}=useAuth()
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[register,setRegister]=useState(false)
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
 const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');setMessage('')
  try{
   if(supabase){
    if(register){const {error}=await supabase.auth.signUp({email,password});if(error)throw error;setMessage('Check your email to confirm your account, if confirmation is enabled.')}
    else{const {data,error}=await supabase.auth.signInWithPassword({email,password});if(error)throw error;if(data.session)setAuth(data.session.access_token,{id:data.user.id,email:data.user.email||email})}
   }else{const res=await api.login('operator@local',password);setAuth(res.access_token,res.user)}
   setPassword('')
  }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
 }
 return <div className="p-8 max-w-2xl space-y-6"><h1 className="text-2xl font-semibold">Account & security</h1>
 <div className="rounded-xl border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-6 space-y-4">
 {token?<><p>Signed in as <strong>{user?.email}</strong></p><button className="rounded-lg border px-4 py-2" onClick={async()=>{if(supabase)await supabase.auth.signOut();logout()}}>Sign out</button></>:
 <form className="space-y-4" onSubmit={submit}><h2>{register?'Create account':'Sign in'}</h2>
 {supabase&&<label className="block text-sm">Email<input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} className="mt-1 block w-full rounded-lg bg-[#0b121b] border border-[#34465b] px-3 py-3"/></label>}
 <label className="block text-sm">Password<input required minLength={supabase?6:1} autoComplete={register?'new-password':'current-password'} type="password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-1 block w-full rounded-lg bg-[#0b121b] border border-[#34465b] px-3 py-3"/></label>
 <button disabled={busy} className="rounded-lg bg-[#bfd4f0] text-[#0b121b] font-semibold px-5 py-2.5">{busy?'Please wait…':register?'Create account':'Sign in'}</button>
 {supabase&&<button type="button" className="ml-4 text-sm underline" onClick={()=>setRegister(!register)}>{register?'Already have an account?':'Create an account'}</button>}</form>}
 {error&&<p role="alert" className="text-red-300 text-sm">{error}</p>}{message&&<p className="text-sm">{message}</p>}</div>
 <p className="text-sm text-[var(--color-text-mid)]">Supabase Auth protects your account. Trading controls remain restricted to configured operators; live orders are disabled.</p></div>
}
