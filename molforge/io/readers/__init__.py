# readers 包：导入即触发 @register
# 注意顺序：专门 reader 先注册，OpenBabel 最后（自动去重）
from . import smi_reader  # noqa: F401
from . import mol_reader  # noqa: F401
from . import glog_reader  # noqa: F401
from . import cube_reader  # noqa: F401
from . import gjf_reader  # noqa: F401
from . import xyz_reader  # noqa: F401
from . import pdb_reader  # noqa: F401
from . import mol2_reader  # noqa: F401
