"""Explicit job preparation; submission only after reviewing generated files."""
from pathlib import Path
from PyQt6.QtCore import QThread,pyqtSignal
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QFileDialog,QTextEdit,QMessageBox,QHBoxLayout
from ..workflows.gromacs_submit import build_gromacs_job,enqueue_gromacs_job,DEFAULT_GMX
from ..runtime import data_dir
class _JobWorker(QThread):
    done=pyqtSignal(object,str)
    def __init__(self,fn,parent):super().__init__(parent);self.fn=fn
    def run(self):
        try:self.done.emit(self.fn(),"")
        except Exception as exc:self.done.emit(None,str(exc))
class GromacsJobDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.job=None;self.worker=None
        self.setWindowTitle("GROMACS 任务准备与队列提交");self.resize(760,440)
        lay=QVBoxLayout(self);form=QFormLayout();lay.addLayout(form)
        self.fields={}
        for key,label,default in [('structure','结构 GRO/PDB',''),('topology','完整拓扑 TOP',''),('gmx_path','GROMACS执行文件',DEFAULT_GMX),('work_dir','独立任务目录',str(data_dir()/'jobs'))]:
            edit=QLineEdit(default);self.fields[key]=edit
            row=QHBoxLayout();row.addWidget(edit);btn=QPushButton('浏览');row.addWidget(btn)
            btn.clicked.connect(lambda _=False,k=key:self.browse(k));form.addRow(label,row)
        self.log=QTextEdit();self.log.setReadOnly(True);lay.addWidget(self.log)
        self.build=QPushButton('生成任务（不入队）');self.submit=QPushButton('确认后加入Pueue队列');self.submit.setEnabled(False)
        lay.addWidget(self.build);lay.addWidget(self.submit);self.build.clicked.connect(self.prepare);self.submit.clicked.connect(self.enqueue)
    def browse(self,key):
        path=QFileDialog.getExistingDirectory(self,'选择目录') if key=='work_dir' else QFileDialog.getOpenFileName(self,'选择文件')[0]
        if path:self.fields[key].setText(path)
    def start(self,fn):
        self.build.setEnabled(False);self.submit.setEnabled(False);self.worker=_JobWorker(fn,self)
        self.worker.done.connect(self.done);self.worker.start()
    def prepare(self):
        args={k:w.text().strip() for k,w in self.fields.items()}
        root=Path(args['work_dir'])
        if root.exists() and any(root.iterdir()):
            QMessageBox.warning(self,'目录非空','请选择新的空任务目录，避免覆盖已有计算。');return
        self.start(lambda:build_gromacs_job(**args))
    def enqueue(self):
        if not self.job:return
        if QMessageBox.question(self,'确认计算任务','将使用GPU资源运行已生成的minim/nvt/md任务。确认完整拓扑、盒子和参数已审核后入队？',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.start(lambda:enqueue_gromacs_job(self.job))
    def done(self,value,error):
        if isinstance(value,dict):self.job=value
        self.log.append(error or str(value));self.build.setEnabled(True);self.submit.setEnabled(self.job is not None and not error)
    def closeEvent(self,e):
        if self.worker and self.worker.isRunning():e.ignore();return
        super().closeEvent(e)
