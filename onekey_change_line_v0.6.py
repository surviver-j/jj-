# -*- coding: utf-8 -*-
"""换线软件同步助手 v0.6
Python 3.10+；标准库实现。打包：pyinstaller --noconsole --onefile --name 换线软件同步助手_v0.6 onekey_change_line_v0.6.py
"""
import os, sys, json, ftplib, hashlib, shutil, socket, tempfile, zipfile, re, threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP = "换线软件同步助手 v0.6"
HOME = Path(os.environ.get("APPDATA", str(Path.home()))) / "ChangeLineSyncAssistant"
HOME.mkdir(parents=True, exist_ok=True)
RULES = HOME / "ini_rules.json"
PROFILES = HOME / "local_profiles.json"
FTPSET = HOME / "ftp_settings.json"

def read_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()

def decode_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "gbk", "utf-8"):
        try: return raw.decode(enc), enc
        except UnicodeError: pass
    raise UnicodeError("无法识别 INI 编码，已停止修改。")

def scan_ini(path):
    text, enc = decode_text(path)
    section, rows = "", []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1].strip()
        elif s and not s.startswith((";", "#")) and "=" in line:
            k, v = line.split("=", 1)
            if k.strip(): rows.append((section, k.strip(), v.strip(), n))
    return rows, enc

def set_ini(path, section, key, value):
    text, enc = decode_text(path)
    lines = text.splitlines(keepends=True)
    cur, hits = "", []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1].strip()
        elif cur == section and "=" in line and not s.startswith((";", "#")):
            if line.split("=", 1)[0].strip() == key: hits.append(i)
    if len(hits) != 1:
        raise ValueError(f"[{section}] 的键 {key} 匹配到 {len(hits)} 次；必须恰好一次，未修改。")
    i = hits[0]
    line = lines[i]
    left, right = line.split("=", 1)
    nl = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    raw = right.rstrip("\r\n")
    cm = re.search(r"(\s+[;#].*)$", raw)
    comment = cm.group(1) if cm else ""
    lead = re.match(r"\s*", right).group(0)
    lines[i] = left + "=" + lead + str(value) + comment + nl
    Path(path).write_bytes("".join(lines).encode(enc))
    rows, _ = scan_ini(path)
    got = [r for r in rows if r[0] == section and r[1] == key]
    if len(got) != 1 or got[0][2] != str(value): raise IOError("INI 写入后校验失败。")

def safe_rel(root, rel):
    p = (Path(root) / rel).resolve()
    if os.path.commonpath([str(Path(root).resolve()), str(p)]) != str(Path(root).resolve()):
        raise ValueError("路径超出部署目录。")
    return p

class FTP:
    def __init__(self, host, port, user, password):
        self.host, self.port, self.user, self.password = host, int(port), user, password
    def __enter__(self):
        self.c = ftplib.FTP()
        self.c.connect(self.host, self.port, timeout=25)
        self.c.login(self.user, self.password)
        self.c.encoding = "utf-8"
        return self
    def __exit__(self, *args):
        try: self.c.quit()
        except Exception: self.c.close()
    def mkdirs(self, remote):
        cur = ""
        for part in [x for x in remote.strip("/").split("/") if x]:
            cur += "/" + part
            try: self.c.cwd(cur)
            except ftplib.all_errors:
                try: self.c.mkd(cur); self.c.cwd(cur)
                except ftplib.all_errors as e: raise RuntimeError(f"无法创建/进入 FTP 目录 {cur}: {e}")
        self.c.cwd("/")
    def put(self, local, remote):
        folder, name = remote.rsplit("/", 1)
        if folder: self.mkdirs(folder)
        with open(local, "rb") as f: self.c.storbinary("STOR " + remote, f)
    def get(self, remote, local):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as f: self.c.retrbinary("RETR " + remote, f.write)

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP); root.geometry("980x720"); root.minsize(850, 620)
        fs = read_json(FTPSET, {})
        self.host=tk.StringVar(value=fs.get("host","")); self.port=tk.StringVar(value=str(fs.get("port",21)))
        self.user=tk.StringVar(value=fs.get("user","")); self.pw=tk.StringVar()
        self.project=tk.StringVar(value="SIM8950"); self.order=tk.StringVar(value="3100008779")
        self.station=tk.StringVar(value="BT"); self.target=tk.StringVar(value=str(Path.home()/"TestSoftware"))
        self.tool=tk.StringVar(value="通用测试工具"); self.rel=tk.StringVar(); self.section=tk.StringVar()
        self.key=tk.StringVar(); self.pname=tk.StringVar(); self.pvalue=tk.StringVar()
        self.rules=read_json(RULES, {}); self.profiles=read_json(PROFILES, {})
        self.rows=[]; self.build()
        self.log(f"启动完成，本机标识：{socket.gethostname()}")

    def build(self):
        ttk.Label(self.root,text=APP,font=("Microsoft YaHei UI",16,"bold")).pack(anchor="w",padx=12,pady=8)
        nb=ttk.Notebook(self.root); nb.pack(fill="both",expand=True,padx=10,pady=5)
        a=ttk.Frame(nb,padding=10); b=ttk.Frame(nb,padding=10); c=ttk.Frame(nb,padding=10)
        nb.add(a,text="FTP 换线部署"); nb.add(b,text="本机 INI 参数"); nb.add(c,text="运行日志")
        self.logbox=tk.Text(c,state="disabled",wrap="word"); self.logbox.pack(fill="both",expand=True)
        fb=ttk.LabelFrame(a,text="FTP 连接",padding=8); fb.pack(fill="x")
        for i,(lab,var,w,show) in enumerate([("服务器",self.host,22,None),("端口",self.port,6,None),("账号",self.user,16,None),("密码",self.pw,16,"*")]):
            ttk.Label(fb,text=lab).grid(row=0,column=i*2,sticky="w")
            ttk.Entry(fb,textvariable=var,width=w,show=show).grid(row=0,column=i*2+1,padx=4,pady=4)
        ttk.Button(fb,text="测试连接",command=self.test).grid(row=0,column=8,padx=4)
        ttk.Button(fb,text="保存连接信息",command=self.save_ftp).grid(row=0,column=9,padx=4)
        pb=ttk.LabelFrame(a,text="项目 / 工单 / 工站",padding=8); pb.pack(fill="x",pady=8)
        for i,(lab,var) in enumerate([("项目",self.project),("工单/版本",self.order),("工站",self.station)]):
            ttk.Label(pb,text=lab).grid(row=0,column=i*2,sticky="w")
            ttk.Entry(pb,textvariable=var,width=22).grid(row=0,column=i*2+1,padx=5,pady=4)
        ttk.Label(pb,text="部署目录").grid(row=1,column=0,sticky="w")
        ttk.Entry(pb,textvariable=self.target).grid(row=1,column=1,columnspan=4,sticky="ew",pady=5)
        ttk.Button(pb,text="选择目录",command=self.pick_target).grid(row=1,column=5,padx=4)
        self.preview=ttk.Label(pb); self.preview.grid(row=2,column=0,columnspan=6,sticky="w")
        for v in (self.project,self.order,self.station): v.trace_add("write",lambda *_:self.update_preview())
        self.update_preview()
        ab=ttk.Frame(a); ab.pack(fill="x",pady=8)
        ttk.Button(ab,text="上传标准软件目录",command=self.upload).pack(side="left",padx=4)
        ttk.Button(ab,text="下载并部署",command=self.deploy).pack(side="left",padx=4)
        ttk.Button(ab,text="只下载 ZIP",command=self.download_only).pack(side="left",padx=4)
        ttk.Label(a,text="部署为合并覆盖，不主动删除目标目录中的其他文件/工站。部署前备份，失败时尝试回滚；SHA-256 文件存在时强制校验。",wraplength=850).pack(anchor="w",pady=5)
        ttk.Label(b,text="先选择真实 INI 文件并扫描，再选中准确的 Section/Key，录入该电脑自己的参数值。程序不会猜测端口或夹具编号的键名。",wraplength=900).pack(anchor="w",pady=4)
        r=ttk.Frame(b); r.pack(fill="x")
        for lab,var,w in [("工具名称",self.tool,20),("INI 相对路径",self.rel,35)]:
            ttk.Label(r,text=lab).pack(side="left",padx=3); ttk.Entry(r,textvariable=var,width=w).pack(side="left",padx=3)
        ttk.Button(r,text="选择并扫描 INI",command=self.scan).pack(side="left",padx=4)
        self.tree=ttk.Treeview(b,columns=("s","k","v","n"),show="headings",height=12)
        for col,title,width in [("s","Section",170),("k","Key",220),("v","当前值",300),("n","行号",60)]:
            self.tree.heading(col,text=title); self.tree.column(col,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True,pady=6); self.tree.bind("<<TreeviewSelect>>",self.select_row)
        e=ttk.Frame(b); e.pack(fill="x")
        for lab,var,w in [("Section",self.section,14),("Key",self.key,18),("参数名称",self.pname,18),("本机参数值",self.pvalue,18)]:
            ttk.Label(e,text=lab).pack(side="left",padx=2); ttk.Entry(e,textvariable=var,width=w).pack(side="left",padx=2)
        buttons=ttk.Frame(b); buttons.pack(fill="x",pady=7)
        for label,fn in [("保存规则和本机值",self.save_rule),("读取本机配置",self.load_profile),("应用到部署目录",self.apply_profile),("删除规则",self.delete_rule)]:
            ttk.Button(buttons,text=label,command=fn).pack(side="left",padx=4)

    def log(self,msg):
        if hasattr(self,"logbox"):
            self.logbox.configure(state="normal"); self.logbox.insert("end",f"[{datetime.now():%F %T}] {msg}\n")
            self.logbox.see("end"); self.logbox.configure(state="disabled")
    def bg(self,fn):
        def run():
            try: fn()
            except Exception as e:
                self.log("失败："+str(e)); self.root.after(0,lambda m=str(e):messagebox.showerror("操作失败",m))
        threading.Thread(target=run,daemon=True).start()
    def ftp_args(self):
        if not self.host.get().strip() or not self.user.get().strip(): raise ValueError("请填写 FTP 服务器和账号。")
        return FTP(self.host.get().strip(),self.port.get() or "21",self.user.get().strip(),self.pw.get())
    def base(self):
        parts=[self.project.get().strip(),self.order.get().strip(),self.station.get().strip()]
        if not all(parts) or any("/" in p or "\\" in p or ".." in p for p in parts): raise ValueError("项目、工单、工站不能为空，且不能包含路径分隔符或 ..")
        return "/".join(parts)
    def update_preview(self):
        if hasattr(self,"preview"): self.preview.configure(text="FTP 路径："+"/".join([self.project.get(),self.order.get(),self.station.get(),"package.zip"]))
    def pick_target(self):
        d=filedialog.askdirectory(title="选择部署目录")
        if d:self.target.set(d)
    def save_ftp(self):
        write_json(FTPSET,{"host":self.host.get().strip(),"port":self.port.get() or "21","user":self.user.get().strip()})
        messagebox.showinfo("完成",f"已保存服务器、端口和账号（不保存密码）：\n{FTPSET}")
    def test(self):
        def work():
            with self.ftp_args(): pass
            self.log("FTP 连接成功。"); self.root.after(0,lambda:messagebox.showinfo("成功","FTP 连接成功。"))
        self.bg(work)
    def upload(self):
        src=filedialog.askdirectory(title="选择标准测试软件目录")
        if not src:return
        if not messagebox.askyesno("确认",f"上传目录到 {self.base()}/package.zip？同一工站的 package.zip 会更新，其他工站目录不会删除。"):return
        def work():
            with tempfile.TemporaryDirectory() as td:
                zpath=Path(td)/"package.zip"
                with zipfile.ZipFile(zpath,"w",zipfile.ZIP_DEFLATED) as z:
                    for root,dirs,files in os.walk(src):
                        dirs[:]=[d for d in dirs if d not in ("__pycache__",)]
                        for name in files:
                            p=Path(root)/name; z.write(p,p.relative_to(src))
                digest=sha256(zpath); base=self.base()
                with self.ftp_args() as c:
                    c.mkdirs(base); c.put(zpath,base+"/package.zip")
                    (Path(td)/"package.zip.sha256").write_text(digest+"  package.zip\n",encoding="ascii")
                    c.put(Path(td)/"package.zip.sha256",base+"/package.zip.sha256")
            self.log("上传成功，SHA-256："+digest)
            self.root.after(0,lambda:messagebox.showinfo("完成","上传成功。\nSHA-256："+digest))
        self.bg(work)
    def fetch_zip(self, local):
        base=self.base()
        with self.ftp_args() as c:
            c.get(base+"/package.zip",local)
            side=str(local)+".sha256"
            try:c.get(base+"/package.zip.sha256",side)
            except ftplib.all_errors:side=None
        actual=sha256(local)
        if side:
            expected=Path(side).read_text(encoding="ascii",errors="ignore").split()[0]
            if expected.lower()!=actual.lower():raise ValueError("SHA-256 校验失败，已停止部署。")
        else:self.log("警告：服务器没有 SHA-256 摘要文件，未能与服务器摘要比对。")
        with zipfile.ZipFile(local) as z:
            if z.testzip():raise ValueError("ZIP 完整性检查失败。")
            basecheck=Path(tempfile.gettempdir(),"clsa_extract_check").resolve()
            for info in z.infolist():
                dest=(basecheck/info.filename).resolve()
                if os.path.commonpath([str(basecheck),str(dest)])!=str(basecheck):raise ValueError("压缩包存在越界路径："+info.filename)
        return actual
    def download_only(self):
        out=filedialog.asksaveasfilename(defaultextension=".zip",initialfile="package.zip",filetypes=[("ZIP","*.zip")])
        if not out:return
        def work():
            d=self.fetch_zip(out);self.log("下载完成："+out)
            self.root.after(0,lambda:messagebox.showinfo("下载完成",f"{out}\nSHA-256: {d}"))
        self.bg(work)
    def deploy(self):
        target=Path(self.target.get().strip())
        if not str(target).strip():messagebox.showwarning("提示","请选择部署目录。");return
        if not messagebox.askyesno("确认部署",f"下载并部署 {self.base()} 到：\n{target}\n\n将备份已有目录，并合并覆盖、不主动删除旧文件。继续？"):return
        def work():
            target.parent.mkdir(parents=True,exist_ok=True)
            backup=target.parent/(target.name+"_backup_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
            with tempfile.TemporaryDirectory() as td:
                archive=str(Path(td)/"package.zip");digest=self.fetch_zip(archive)
                extract=Path(td)/"extract";extract.mkdir()
                with zipfile.ZipFile(archive) as z:z.extractall(extract)
                existed=target.exists()
                try:
                    if existed:shutil.copytree(target,backup)
                    target.mkdir(parents=True,exist_ok=True)
                    for root,dirs,files in os.walk(extract):
                        rel=Path(root).relative_to(extract); dest=target/rel;dest.mkdir(parents=True,exist_ok=True)
                        for d in dirs:(dest/d).mkdir(parents=True,exist_ok=True)
                        for name in files:shutil.copy2(Path(root)/name,dest/name)
                    with zipfile.ZipFile(archive) as z:
                        for info in z.infolist():
                            if not info.is_dir() and sha256(target/info.filename)!=hashlib.sha256(z.read(info.filename)).hexdigest():raise IOError("部署校验失败："+info.filename)
                    self.log("部署成功："+str(target))
                    self.root.after(0,lambda:messagebox.showinfo("完成",f"部署和文件校验成功。\n目录：{target}\n备份：{backup if existed else '首次部署'}\nSHA-256：{digest}\n如需本机参数，请进入 INI 参数页应用。"))
                except Exception:
                    self.log("部署失败，执行回滚。")
                    if target.exists():shutil.rmtree(target)
                    if existed and backup.exists():shutil.copytree(backup,target)
                    raise
        self.bg(work)
    def scan(self):
        p=filedialog.askopenfilename(title="选择 INI/TXT 配置文件",initialdir=self.target.get() if Path(self.target.get()).exists() else str(Path.home()),filetypes=[("配置文件","*.ini *.txt"),("所有文件","*.*")])
        if not p:return
        try: rows,enc=scan_ini(p)
        except Exception as e:messagebox.showerror("读取失败",str(e));return
        self.rows=rows;self.tree.delete(*self.tree.get_children())
        root=Path(self.target.get()) if Path(self.target.get()).exists() else Path(p).parent
        try:rel=str(Path(p).resolve().relative_to(root.resolve()))
        except ValueError:rel=os.path.relpath(p,root)
        self.rel.set(rel.replace("\\","/"))
        for i,row in enumerate(rows):self.tree.insert("","end",iid=str(i),values=row)
        self.log(f"扫描 {p}，编码 {enc}，识别到 {len(rows)} 个键值。")
    def select_row(self,_=None):
        sel=self.tree.selection()
        if sel:
            s,k,v,n=self.tree.item(sel[0],"values")
            self.section.set(s);self.key.set(k);self.pname.set(self.pname.get() or k);self.pvalue.set(v)
    def save_rule(self):
        tool,rel,s,k=[x.get().strip() for x in (self.tool,self.rel,self.section,self.key)]
        if not all((tool,rel,s,k)):messagebox.showwarning("提示","工具名称、相对路径、Section、Key 必填。");return
        rule={"file":rel,"section":s,"key":k,"name":self.pname.get().strip() or k}
        rs=self.rules.setdefault(tool,[]);rs[:]=[x for x in rs if (x["file"],x["section"],x["key"])!=(rel,s,k)];rs.append(rule)
        host=self.profiles.setdefault(socket.gethostname(),{}).setdefault(tool,{})
        host[rel+"|"+s+"|"+k]=self.pvalue.get()
        write_json(RULES,self.rules);write_json(PROFILES,self.profiles)
        self.log(f"规则和本机参数已保存：{tool} {rel} [{s}] {k}")
        messagebox.showinfo("保存成功",f"规则及本机值已保存。\n{RULES}\n{PROFILES}")
    def load_profile(self):
        tool=self.tool.get().strip(); vals=self.profiles.get(socket.gethostname(),{}).get(tool,{})
        rules=self.rules.get(tool,[])
        if not rules:messagebox.showwarning("提示","请先扫描并保存该工具的规则。");return
        for r in rules:
            k=r["file"]+"|"+r["section"]+"|"+r["key"]
            if k in vals:
                self.rel.set(r["file"]);self.section.set(r["section"]);self.key.set(r["key"]);self.pname.set(r.get("name",r["key"]));self.pvalue.set(vals[k]);break
        messagebox.showinfo("读取完成",f"本机：{socket.gethostname()}\n规则数：{len(rules)}")
    def apply_profile(self):
        root=Path(self.target.get().strip());tool=self.tool.get().strip()
        rules=self.rules.get(tool,[]);vals=self.profiles.get(socket.gethostname(),{}).get(tool,{})
        if not rules:messagebox.showwarning("提示","没有规则，请先扫描并保存。");return
        if not messagebox.askyesno("确认",f"对 {root} 应用 {len(rules)} 条本机参数？遇到错误将恢复本次涉及的 INI 文件。"):return
        originals={}
        try:
            for r in rules:
                k=r["file"]+"|"+r["section"]+"|"+r["key"]
                if k not in vals:continue
                p=safe_rel(root,r["file"])
                if not p.is_file():raise FileNotFoundError("找不到配置文件："+str(p))
                if str(p) not in originals:originals[str(p)]=p.read_bytes()
                set_ini(p,r["section"],r["key"],vals[k])
            self.log("本机参数应用成功。");messagebox.showinfo("完成","本机参数已应用并校验。")
        except Exception as e:
            failed=[]
            for p,data in originals.items():
                try:Path(p).write_bytes(data)
                except Exception as re_err:failed.append(p+" ("+str(re_err)+")")
            self.log("参数应用失败，已尝试恢复："+str(e))
            messagebox.showerror("应用失败",str(e)+("\n恢复失败文件："+", ".join(failed) if failed else "\n已恢复本次修改涉及的文件。"))
    def delete_rule(self):
        tool,rel,s,k=[x.get().strip() for x in (self.tool,self.rel,self.section,self.key)]
        rs=self.rules.get(tool,[]);n=len(rs);rs[:]=[r for r in rs if (r["file"],r["section"],r["key"])!=(rel,s,k)]
        if len(rs)==n:messagebox.showwarning("提示","没有匹配规则。");return
        write_json(RULES,self.rules);self.log("规则已删除（不会删除 INI 中的内容）。")
        messagebox.showinfo("完成","规则已删除。")

def main():
    root=tk.Tk()
    try:ttk.Style().theme_use("vista")
    except tk.TclError:pass
    App(root);root.mainloop()
if __name__=="__main__":main()
