import os, html, uuid, requests, streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

# ----------------- Config backend -----------------
BACKEND_URL      = os.getenv("BACKEND_URL", "http://localhost:8000")
ASK_URL          = f"{BACKEND_URL}/ask"
REINDEX_URL      = f"{BACKEND_URL}/reindex"
DOCS_UPLOAD_URL  = f"{BACKEND_URL}/upload"
LIST_UPLOADS_URL = f"{BACKEND_URL}/list_user_uploads"
HEALTH_URL       = f"{BACKEND_URL}/healthcheck"

# ----------------- Page setup -----------------
st.set_page_config(page_title="Upfund", page_icon="🧠", layout="wide")

# ----------------- Styles (noir & blanc + corrections UI) -----------------
st.markdown("""
<style>
:root{ --bg:#000; --bg2:#0f0f0f; --bg3:#151515; --fg:#fff; --muted:#bfbfbf; --border:#2a2a2a; --border2:#3a3a3a; }
html, body, [data-testid="stAppViewContainer"]{
  background:var(--bg)!important; color:var(--fg)!important;
  font-family:Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial!important;
}
h1,h2,h3,h4,h5,h6,p,span,div,label{ color:var(--fg)!important; }
section[data-testid="stSidebar"]{ background:var(--bg2)!important; border-right:1px solid var(--border)!important; }

/* Titre centré */
h1#upfund-chat { text-align:center; }

/* Inputs / boutons */
input, textarea, .stTextInput > div > div > input, .stTextArea > div > div > textarea {
  background:var(--bg3)!important; color:var(--fg)!important; border:1px solid var(--border2)!important; border-radius:10px!important;
}
.stButton>button, .stForm button[type="submit"]{
  background:transparent!important; color:var(--fg)!important; border:1px solid var(--border2)!important; border-radius:10px!important;
}
.stButton>button:hover, .stForm button[type="submit"]:hover{ background:#111!important; }

/* Chat */
.chat-container{ max-width:900px; margin:0 auto; padding:12px 0 120px; }
.chat-row{ display:flex; margin:10px 0; }
.chat-row.user{ justify-content:flex-end; }
.chat-row.assistant{ justify-content:flex-start; }
.chat-bubble{ max-width:75%; padding:14px 16px; border-radius:16px; word-wrap:break-word; line-height:1.5; background:var(--bg3); border:1px solid var(--border); }
.chat-bubble.user{ background:transparent; border:1px solid #e5e5e5; color:var(--fg); border-bottom-right-radius:6px; }
.chat-bubble.assistant{ border-bottom-left-radius:6px; }

/* Sources */
.source-card{ border:1px solid var(--border); border-radius:10px; padding:10px; margin:6px 0; background:var(--bg2); }
.source-file{ color:#f5f5f5; font-weight:600; }
.source-pre{ background:var(--bg); border-left:3px solid #e5e5e5; padding:8px; border-radius:6px; font-family:ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono"; white-space:pre-wrap; }

/* Uploads list */
.doc-item{ display:flex; align-items:center; justify-content:space-between; border:1px solid var(--border); border-radius:10px; padding:10px; margin:6px 0; background:var(--bg3); }
.doc-left{ display:flex; gap:10px; align-items:center; flex:1; min-width:0; }
.doc-name{ font-weight:600; display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:100%; }
.doc-size{ color:var(--muted); font-size:12px; flex-shrink:0; }

/* Chat titles (historique): 1 ligne + ellipsis, pas de wrap */
.chat-title-btn > button{
  width:100%;
  white-space:nowrap !important;
  overflow:hidden !important;
  text-overflow:ellipsis !important;
  display:block;
}

/* Input bar sticky bottom */
.input-bar{ position:fixed; bottom:0; left:0; right:0; background:var(--bg); border-top:1px solid var(--border); padding:14px 0; }
</style>
""", unsafe_allow_html=True)

# ----------------- State -----------------
if "k" not in st.session_state: st.session_state.k = 2
if "chats" not in st.session_state: st.session_state.chats = {}
if "current_chat_id" not in st.session_state:
    cid = str(uuid.uuid4())
    st.session_state.current_chat_id = cid
    st.session_state.chats[cid] = {"title":"New chat","created_at": datetime.now(),"messages":[]}
if "awaiting" not in st.session_state: st.session_state.awaiting = None
if "last_render_count" not in st.session_state: st.session_state.last_render_count = 0  # pour autoscroll

# ----------------- Helpers -----------------
def human_size(n:int)->str:
    units=["B","KB","MB","GB"]; i=0; f=float(n)
    while f>=1024 and i<3: f/=1024; i+=1
    return f"{f:.1f} {units[i]}"

def chat_title(messages)->str:
    first = next((m for m in messages if m["role"]=="user"), None)
    if not first: return "New chat"
    t = first["content"].strip()
    return (t[:60]+"…") if len(t)>62 else t

def new_chat():
    cid = str(uuid.uuid4())
    st.session_state.current_chat_id = cid
    st.session_state.chats[cid] = {"title":"New chat","created_at": datetime.now(),"messages":[]}
    st.rerun()

def switch_chat(cid:str):
    if cid in st.session_state.chats:
        st.session_state.current_chat_id = cid
        st.rerun()

def delete_chat(cid:str):
    if len(st.session_state.chats) <= 1: return
    del st.session_state.chats[cid]
    st.session_state.current_chat_id = next(iter(st.session_state.chats.keys()))
    st.rerun()

def fetch_user_uploads():
    try:
        resp = requests.get(LIST_UPLOADS_URL, timeout=8)
        if resp.ok:
            data = resp.json()
            return [(d["path"], int(d.get("size",0))) for d in data.get("docs",[])]
    except Exception:
        pass
    return []

def autoscroll():
    """Scroll en bas sans perdre la position : ne s’exécute que si
       le nombre de blocs rendus a augmenté (nouveau message)."""
    components.html(
        """
        <script>
        window.setTimeout(function(){
           var el = document.querySelector('div.chat-container');
           if(el){ el.scrollTop = el.scrollHeight; }
           // fallback: scroll page
           window.scrollTo(0, document.body.scrollHeight);
        }, 10);
        </script>
        """, height=0
    )

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.session_state.k = st.slider("Top-k", 1, 20, st.session_state.k)
    c1,c2 = st.columns(2)
    with c1:
        if st.button("Health"):
            try:
                r = requests.get(HEALTH_URL, timeout=8)
                st.success("OK" if r.ok else f"Err {r.status_code}")
                if r.ok: st.caption(r.json())
            except Exception as e:
                st.error(f"{e}")
    with c2:
        if st.button("Reindex all"):
            r = requests.post(REINDEX_URL, json={"clear": False})
            st.success("Reindexed") if r.ok else st.error(r.text)

    st.markdown("---")
    up_files = st.file_uploader("Ajouter (pdf/docx/txt)", type=["pdf","docx","txt"], accept_multiple_files=True, key="uploader")
    if st.button("Upload & index", use_container_width=True):
        if not up_files:
            st.warning("Sélectionne au moins un fichier.")
        else:
            ok=0
            prog = st.progress(0)
            for i,f in enumerate(up_files):
                try:
                    resp = requests.post(DOCS_UPLOAD_URL, files={"file": (f.name, f.getvalue())}, timeout=60)
                    if resp.ok: ok+=1
                    else: st.error(f"{f.name}: {resp.text}")
                except Exception as e:
                    st.error(f"{f.name}: {e}")
                prog.progress(int((i+1)/len(up_files)*100))
            prog.empty()
            if ok: st.success(f"{ok}/{len(up_files)} uploadés & indexés ✔")
            st.rerun()

    # Liste uniquement des uploads manuels
    st.markdown("### 📁 Uploads")
    docs = fetch_user_uploads()
    if docs:
        for rel, sz in docs[:200]:
            icon = "📄" if rel.lower().endswith(".pdf") else ("📝" if rel.lower().endswith(".docx") else "📋")
            st.markdown(f"""
            <div class="doc-item">
              <div class="doc-left">
                <span>{icon}</span>
                <div style="min-width:0;">
                  <div class="doc-name" title="{html.escape(rel)}">{html.escape(rel)}</div>
                  <div class="doc-size">{human_size(sz)}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Aucun upload pour l’instant.")

    st.markdown("---")
    st.markdown("### 💬 Chats")
    if st.button("➕ New chat", use_container_width=True): new_chat()
    for cid, meta in sorted(st.session_state.chats.items(), key=lambda kv: kv[1]["created_at"], reverse=True):
        is_active = (cid == st.session_state.current_chat_id)
        title = chat_title(meta["messages"])
        date_str = meta["created_at"].strftime("%d/%m %H:%M")
        cA, cB = st.columns([5,1])
        short_title = (title[:20] + "..." if len(title) > 23 else title)
        with cA:
            if st.container(border=False).button(short_title,
                                     key=f"chat_{cid}", use_container_width=True,
                                     help=title):
                switch_chat(cid)
            st.markdown("<style>.stButton button {white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}</style>",
                        unsafe_allow_html=True)
        with cB:
            if len(st.session_state.chats)>1 and st.button("🗑", key=f"del_{cid}"):
                delete_chat(cid)
        #st.caption(f"{date_str}")

# ----------------- MAIN -----------------
st.markdown("# Upfund Chat", unsafe_allow_html=True)  # h1 centré via CSS (#upfund-chat)

# Conversation
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
cur = st.session_state.chats[st.session_state.current_chat_id]
msgs = cur["messages"]

# Compte avant rendu (pour savoir si on ajoute un msg -> autoscroll)
before = len(msgs)

# Rendu messages
for m in msgs:
    role = "user" if m["role"]=="user" else "assistant"
    content = html.escape(m["content"])
    st.markdown(
        f'<div class="chat-row {role}"><div class="chat-bubble {role}">{content}</div></div>',
        unsafe_allow_html=True
    )
    if m.get("sources"):
        for s in m["sources"]:
            fname = html.escape(str(s.get("file","")))
            sc = float(s.get("score") or 0.0)
            snip = html.escape(s.get("snippet",""))
            st.markdown(
                f'<div class="source-card"><div class="source-file">{fname} • score {sc:.4f}</div>'
                f'<div class="source-pre">{snip}</div></div>',
                unsafe_allow_html=True
            )

st.markdown('</div>', unsafe_allow_html=True)

# ----------------- Input collé en bas -----------------
st.markdown('<div class="input-bar">', unsafe_allow_html=True)
with st.form("chat_form", clear_on_submit=True):
    c1, c2 = st.columns([6,1])
    with c1:
        user_q = st.text_input("", placeholder="💭 Pose ta question…",
                               label_visibility="collapsed", key="q_input")
    with c2:
        send = st.form_submit_button("Envoyer", use_container_width=True)

# Submit : on affiche TOUT DE SUITE le message et on programme la requête
if send and user_q.strip():
    q = user_q.strip()
    cur["messages"].append({"role":"user","content": q})
    if len(cur["messages"]) == 1:
        cur["title"] = chat_title(cur["messages"])
    st.session_state.chats[st.session_state.current_chat_id] = cur
    st.session_state.awaiting = {"question": q, "k": st.session_state.k}
    # autoscroll immédiatement (sans perdre la position)
    autoscroll()
    st.rerun()

# Si un nouveau message a été rendu (après réponse), autoscroll
after = len(cur["messages"])
if after > before:
    autoscroll()

st.markdown('</div>', unsafe_allow_html=True)

# ----------------- Appel backend APRÈS rendu (pour garder l’ancrage) -----------------
if st.session_state.awaiting:
    payload = st.session_state.awaiting
    with st.spinner("Réflexion en cours…"):
        try:
            r = requests.post(ASK_URL, json={"question": payload["question"], "k": payload["k"]}, timeout=60)
            if r.ok:
                data = r.json()
                cur["messages"].append({
                    "role":"assistant",
                    "content": data.get("answer",""),
                    "sources": data.get("sources",[])
                })
            else:
                cur["messages"].append({"role":"assistant","content": f"❌ Erreur: {r.status_code} — {r.text}"})
        except Exception as e:
            cur["messages"].append({"role":"assistant","content": f"❌ Connexion impossible: {e}"})
    st.session_state.chats[st.session_state.current_chat_id] = cur
    st.session_state.awaiting = None
    # autoscroll quand la réponse arrive
    autoscroll()
    st.rerun()
