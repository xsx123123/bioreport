"""Post-render PDF protection: AES-256 permission lock without an open password.

The user password stays empty so clients open and print the report directly;
the owner password (from config or the BIOREPORT_OWNER_SECRET environment
variable) locks editing, page manipulation and annotation. Text extraction
stays enabled so researchers can copy gene IDs into NCBI or Ensembl.
"""
import os
from pathlib import Path


def lock_pdf_permissions(
    pdf_path: str | Path,
    owner_password: str,
    allow_copy_text: bool = True,
    allow_print: bool = True,
) -> None:
    """Encrypt the rendered PDF in place with AES-256 (R=6) permissions.

    Raises ImportError when pikepdf is not installed; callers treat the lock
    as optional and keep the unprotected PDF rather than failing the report.
    """
    import pikepdf

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"未找到待加密的 PDF 文件: {pdf_path}")

    permissions = pikepdf.Permissions(
        modify_other=False,        # 禁止编辑文档内容(文字、图表)
        modify_assembly=False,     # 禁止插入、删除、旋转或拆分页面
        modify_annotation=False,    # 禁止添加批注、签名或高亮修改
        modify_form=False,         # 禁止修改表单字段
        extract=allow_copy_text,   # 允许复制基因 ID 等文本,便于检索
        accessibility=True,        # 允许屏幕阅读器辅助访问
        print_lowres=allow_print,
        print_highres=allow_print,
    )
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata() as meta:
            meta["pdf:Producer"] = "BioReport Secure PDF Engine (Protected)"
        pdf.save(
            pdf_path,
            encryption=pikepdf.Encryption(
                user="",                # 免密直接打开阅读
                owner=owner_password,   # 解锁编辑权限的口令
                allow=permissions,
                R=6,                    # 256-bit AES
            ),
        )


def resolve_owner_password(security: dict) -> str | None:
    """Owner password from config; supports indirection via environment variables.

    ``owner_password_env`` names an environment variable holding the secret so
    the password never lands in the report config file or git history.
    """
    if not isinstance(security, dict):
        return None
    if security.get("owner_password"):
        return str(security["owner_password"])
    env_name = security.get("owner_password_env") or "BIOREPORT_OWNER_SECRET"
    value = os.environ.get(env_name)
    return value or None


def protect_report_pdf(pdf_path: str | Path, config: dict) -> bool:
    """Apply the read-only lock when the config requests it.

    Returns True when the PDF was encrypted. Any failure (missing pikepdf,
    empty password, pikepdf error) logs a warning and leaves the PDF usable —
    protection is a delivery hardening step, not a render blocker.
    """
    import logging

    security = (config.get("report") or {}).get("security") or {}
    if not security.get("enable_read_only_lock"):
        return False
    password = resolve_owner_password(security)
    if not password:
        logging.getLogger("bioreport").warning(
            "已请求 PDF 只读加密,但未提供 owner 密码(owner_password 或 %s 环境变量);跳过加密",
            security.get("owner_password_env") or "BIOREPORT_OWNER_SECRET",
        )
        return False
    try:
        lock_pdf_permissions(
            pdf_path,
            password,
            allow_copy_text=security.get("allow_copy_text", True),
            allow_print=security.get("allow_print", True),
        )
    except ImportError:
        logging.getLogger("bioreport").warning("未安装 pikepdf,跳过 PDF 只读加密(pip install pikepdf)")
        return False
    except Exception as exc:
        logging.getLogger("bioreport").warning(f"PDF 加密失败(保留未加密版本): {exc}")
        return False
    return True
