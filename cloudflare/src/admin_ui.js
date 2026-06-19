export const ADMIN_HTML = `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RunLab Scanner - Admin License & Update</title>
<style>
  :root{color-scheme:dark;--bg:#0f172a;--panel:#111827;--panel2:#1f2937;--text:#e5e7eb;--muted:#94a3b8;--accent:#38bdf8;--ok:#22c55e;--bad:#ef4444;--border:#334155;}
  *{box-sizing:border-box;}
  body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:linear-gradient(180deg,#020617,#0f172a);color:var(--text);}
  .wrap{max-width:1100px;margin:0 auto;padding:24px 18px 60px;}
  h1{margin:0 0 4px;} h2{margin:0 0 12px;}
  .muted{color:var(--muted);}
  .panel{background:rgba(17,24,39,.95);border:1px solid var(--border);border-radius:16px;padding:18px;margin-bottom:18px;box-shadow:0 16px 40px rgba(0,0,0,.3);}
  label{display:block;font-size:12px;color:var(--muted);margin:8px 0 4px;}
  input,select,textarea,button{width:100%;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:9px 12px;font-size:14px;}
  .grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
  button{cursor:pointer;width:auto;}
  button.primary{background:var(--accent);color:#082f49;border-color:transparent;font-weight:bold;}
  button.danger{background:transparent;color:var(--bad);border-color:var(--bad);}
  button.ghost{background:transparent;color:var(--accent);border-color:var(--accent);}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{text-align:left;padding:8px 8px;border-bottom:1px solid var(--border);vertical-align:top;}
  th{color:var(--muted);font-weight:600;}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;border:1px solid var(--border);}
  .pill.active{color:var(--ok);border-color:var(--ok);}
  .pill.revoked,.pill.expired{color:var(--bad);border-color:var(--bad);}
  code{background:#0b1220;padding:2px 6px;border-radius:6px;}
  .hidden{display:none;}
  .toast{position:fixed;bottom:18px;right:18px;background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:12px 16px;max-width:360px;}
  .tabs{display:flex;gap:8px;margin-bottom:16px;}
  .tabs button{width:auto;}
  .tabs button.active{background:var(--accent);color:#082f49;border-color:transparent;font-weight:bold;}
</style>
</head>
<body>
<div class="wrap">
  <h1>RunLab Scanner Admin</h1>
  <p class="muted">Kelola license dan rilis update aplikasi.</p>

  <div id="loginPanel" class="panel">
    <h2>Login Admin</h2>
    <label>Admin Token</label>
    <input id="tokenInput" type="password" placeholder="Masukkan ADMIN_TOKEN">
    <div class="row" style="margin-top:12px;">
      <button class="primary" onclick="login()">Masuk</button>
    </div>
  </div>

  <div id="app" class="hidden">
    <div class="tabs">
      <button id="tabLic" class="active" onclick="showTab('lic')">Licenses</button>
      <button id="tabRel" onclick="showTab('rel')">Releases</button>
      <button class="ghost" onclick="logout()" style="margin-left:auto;">Logout</button>
    </div>

    <div id="licView">
      <div class="panel">
        <h2>Buat License Baru</h2>
        <div class="grid">
          <div><label>Nama Customer</label><input id="cName"></div>
          <div><label>Email</label><input id="cEmail"></div>
          <div><label>Max Aktivasi</label><input id="cMax" type="number" value="1" min="1"></div>
          <div><label>Channel</label><select id="cChannel"><option value="stable">stable</option><option value="beta">beta</option></select></div>
          <div><label>Expires (YYYY-MM-DD, kosong=selamanya)</label><input id="cExpires" placeholder="2027-12-31"></div>
          <div><label>License Key (kosong=auto)</label><input id="cKey" placeholder="auto-generate"></div>
        </div>
        <label>Catatan</label><input id="cNotes">
        <div class="row" style="margin-top:12px;"><button class="primary" onclick="createLicense()">Generate License</button></div>
      </div>
      <div class="panel">
        <h2>Daftar License</h2>
        <div style="overflow-x:auto;"><table id="licTable"><thead><tr>
          <th>Key</th><th>Customer</th><th>Status</th><th>Aktivasi</th><th>Channel</th><th>Expires</th><th>Aksi</th>
        </tr></thead><tbody></tbody></table></div>
      </div>
    </div>

    <div id="relView" class="hidden">
      <div class="panel">
        <h2>Publish Release Baru</h2>
        <div class="grid">
          <div><label>Versi</label><input id="rVersion" placeholder="1.1.0"></div>
          <div><label>Channel</label><select id="rChannel"><option value="stable">stable</option><option value="beta">beta</option></select></div>
          <div><label>Mandatory?</label><select id="rMandatory"><option value="0">Tidak</option><option value="1">Ya</option></select></div>
        </div>
        <label>URL EXE (kosongkan jika pakai Object Key)</label><input id="rUrl" placeholder="https://cdn.../RunLabScanner-1.1.0.exe">
        <label>Object Key R2 (opsional, dibentuk dari PUBLIC_BASE_URL)</label><input id="rKey" placeholder="runlab-scanner/releases/RunLabScanner-1.1.0.exe">
        <label>Catatan Update</label><textarea id="rNotes" rows="3"></textarea>
        <div class="row" style="margin-top:12px;"><button class="primary" onclick="createRelease()">Publish</button></div>
      </div>
      <div class="panel">
        <h2>Riwayat Release</h2>
        <div style="overflow-x:auto;"><table id="relTable"><thead><tr>
          <th>Versi</th><th>Channel</th><th>Mandatory</th><th>URL</th><th>Tanggal</th>
        </tr></thead><tbody></tbody></table></div>
      </div>
    </div>
  </div>
</div>
<div id="toast" class="toast hidden"></div>

<script>
let TOKEN = sessionStorage.getItem("rls_admin_token") || "";

function toast(msg, ms=3500){
  const t=document.getElementById("toast");
  t.textContent=msg; t.classList.remove("hidden");
  setTimeout(()=>t.classList.add("hidden"), ms);
}
function authHeaders(){ return { "Authorization":"Bearer "+TOKEN, "Content-Type":"application/json" }; }

async function api(path, opts={}){
  const res = await fetch(path, { ...opts, headers:{ ...authHeaders(), ...(opts.headers||{}) }});
  const data = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(data.error || ("HTTP "+res.status));
  return data;
}

async function login(){
  TOKEN = document.getElementById("tokenInput").value.trim();
  if(!TOKEN){ toast("Token kosong"); return; }
  try{
    await api("/admin/api/licenses");
    sessionStorage.setItem("rls_admin_token", TOKEN);
    document.getElementById("loginPanel").classList.add("hidden");
    document.getElementById("app").classList.remove("hidden");
    loadLicenses(); loadReleases();
  }catch(e){ toast("Login gagal: "+e.message); TOKEN=""; }
}
function logout(){ sessionStorage.removeItem("rls_admin_token"); location.reload(); }

function showTab(which){
  document.getElementById("licView").classList.toggle("hidden", which!=="lic");
  document.getElementById("relView").classList.toggle("hidden", which!=="rel");
  document.getElementById("tabLic").classList.toggle("active", which==="lic");
  document.getElementById("tabRel").classList.toggle("active", which==="rel");
}

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c])); }

async function loadLicenses(){
  try{
    const { licenses } = await api("/admin/api/licenses");
    const tb = document.querySelector("#licTable tbody"); tb.innerHTML="";
    for(const l of licenses){
      const tr=document.createElement("tr");
      tr.innerHTML =
        "<td><code>"+esc(l.license_key)+"</code></td>"+
        "<td>"+esc(l.customer_name)+"<br><span class='muted'>"+esc(l.customer_email)+"</span></td>"+
        "<td><span class='pill "+esc(l.status)+"'>"+esc(l.status)+"</span></td>"+
        "<td>"+l.activation_count+" / "+l.max_activations+"</td>"+
        "<td>"+esc(l.channel)+"</td>"+
        "<td>"+esc(l.expires_at||"-")+"</td>"+
        "<td class='row'>"+
          (l.status==="active"
            ? "<button class='danger' onclick=\\"setStatus("+l.id+",'revoke')\\">Revoke</button>"
            : "<button class='ghost' onclick=\\"setStatus("+l.id+",'activate')\\">Aktifkan</button>")+
          "<button class='danger' onclick=\\"delLicense("+l.id+")\\">Hapus</button>"+
        "</td>";
      tb.appendChild(tr);
    }
    if(!licenses.length) tb.innerHTML="<tr><td colspan='7' class='muted'>Belum ada license.</td></tr>";
  }catch(e){ toast("Gagal memuat license: "+e.message); }
}

async function createLicense(){
  const body={
    customer_name:document.getElementById("cName").value,
    customer_email:document.getElementById("cEmail").value,
    max_activations:Number(document.getElementById("cMax").value||1),
    channel:document.getElementById("cChannel").value,
    expires_at:document.getElementById("cExpires").value.trim()||null,
    license_key:document.getElementById("cKey").value.trim(),
    notes:document.getElementById("cNotes").value
  };
  try{
    const r=await api("/admin/api/licenses",{method:"POST",body:JSON.stringify(body)});
    toast("License dibuat: "+r.license_key);
    document.getElementById("cKey").value="";
    loadLicenses();
  }catch(e){ toast("Gagal: "+e.message); }
}

async function setStatus(id, action){
  try{ await api("/admin/api/licenses/"+id+"/"+action,{method:"POST"}); loadLicenses(); }
  catch(e){ toast("Gagal: "+e.message); }
}
async function delLicense(id){
  if(!confirm("Hapus license ini beserta aktivasinya?")) return;
  try{ await api("/admin/api/licenses/"+id,{method:"DELETE"}); loadLicenses(); }
  catch(e){ toast("Gagal: "+e.message); }
}

async function loadReleases(){
  try{
    const { releases } = await api("/admin/api/releases");
    const tb=document.querySelector("#relTable tbody"); tb.innerHTML="";
    for(const r of releases){
      const tr=document.createElement("tr");
      tr.innerHTML="<td>"+esc(r.version)+"</td><td>"+esc(r.channel)+"</td><td>"+(r.mandatory?"Ya":"Tidak")+"</td>"+
        "<td style='max-width:320px;word-break:break-all;'><a href='"+esc(r.url)+"' target='_blank'>"+esc(r.url)+"</a></td>"+
        "<td>"+esc(r.created_at)+"</td>";
      tb.appendChild(tr);
    }
    if(!releases.length) tb.innerHTML="<tr><td colspan='5' class='muted'>Belum ada release.</td></tr>";
  }catch(e){ toast("Gagal memuat release: "+e.message); }
}

async function createRelease(){
  const body={
    version:document.getElementById("rVersion").value.trim(),
    channel:document.getElementById("rChannel").value,
    mandatory:document.getElementById("rMandatory").value==="1",
    url:document.getElementById("rUrl").value.trim(),
    object_key:document.getElementById("rKey").value.trim(),
    notes:document.getElementById("rNotes").value
  };
  try{
    const r=await api("/admin/api/releases",{method:"POST",body:JSON.stringify(body)});
    toast("Release dipublish: "+r.version);
    loadReleases();
  }catch(e){ toast("Gagal: "+e.message); }
}

if(TOKEN){
  document.getElementById("loginPanel").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  loadLicenses(); loadReleases();
}
</script>
</body>
</html>`;
