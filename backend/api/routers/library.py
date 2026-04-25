import uuid
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from backend.database import get_conn
from backend.config import settings

router = APIRouter()


class SaveReportRequest(BaseModel):
    symbol: str
    company: Optional[str] = None
    report_type: str          # 'deep' | 'quick'
    analyst: Optional[str] = None
    content: str
    sources: Optional[str] = None   # JSON string


class SaveNoteRequest(BaseModel):
    symbol: str
    report_id: Optional[str] = None
    analyst: Optional[str] = None
    content: str


# ── Reports ─────────────────────────────────────────────────────────

@router.post('/reports')
def save_report(req: SaveReportRequest):
    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO research_reports (id, symbol, company, report_type, analyst, content, sources, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, req.symbol.upper(), req.company, req.report_type,
             req.analyst, req.content, req.sources, now)
        )
        conn.commit()
    finally:
        conn.close()
    return {'id': report_id, 'created_at': now}


@router.get('/reports')
def list_reports(symbol: Optional[str] = None, report_type: Optional[str] = None,
                 analyst: Optional[str] = None, limit: int = 100):
    conn = get_conn()
    try:
        clauses, params = [], []
        if symbol:      clauses.append('symbol = ?');      params.append(symbol.upper())
        if report_type: clauses.append('report_type = ?'); params.append(report_type)
        if analyst:     clauses.append('analyst = ?');     params.append(analyst)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = conn.execute(
            f"SELECT id, symbol, company, report_type, analyst, sources, created_at FROM research_reports {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get('/reports/{report_id}')
def get_report(report_id: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM research_reports WHERE id = ?", (report_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Report not found')
        return dict(row)
    finally:
        conn.close()


@router.delete('/reports/{report_id}')
def delete_report(report_id: str):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM research_notes WHERE report_id = ?", (report_id,))
        conn.execute("DELETE FROM research_reports WHERE id = ?", (report_id,))
        conn.commit()
    finally:
        conn.close()
    return {'ok': True}


# ── Notes ────────────────────────────────────────────────────────────

@router.post('/notes')
def save_note(req: SaveNoteRequest):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO research_notes (report_id, symbol, analyst, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (req.report_id, req.symbol.upper(), req.analyst, req.content, now)
        )
        conn.commit()
        note_id = cur.lastrowid
    finally:
        conn.close()
    return {'id': note_id, 'created_at': now}


@router.get('/notes')
def list_notes(symbol: Optional[str] = None, report_id: Optional[str] = None):
    conn = get_conn()
    try:
        clauses, params = [], []
        if symbol:    clauses.append('symbol = ?');    params.append(symbol.upper())
        if report_id: clauses.append('report_id = ?'); params.append(report_id)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = conn.execute(
            f"SELECT * FROM research_notes {where} ORDER BY created_at DESC",
            params
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.delete('/notes/{note_id}')
def delete_note(note_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM research_notes WHERE id = ?", (note_id,))
        conn.commit()
    finally:
        conn.close()
    return {'ok': True}


# ── Email ─────────────────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    report_id: str
    to_emails: List[str]
    subject: str
    body: str              # HTML or plain text email body


def _markdown_to_html(md: str) -> str:
    """Minimal markdown → HTML for email."""
    lines = md.split('\n')
    html = []
    for line in lines:
        if line.startswith('### '): html.append(f'<h3 style="color:#1a1a2e;margin:12px 0 4px">{line[4:]}</h3>')
        elif line.startswith('## '): html.append(f'<h2 style="color:#1a1a2e;border-bottom:1px solid #eee;padding-bottom:4px">{line[3:]}</h2>')
        elif line.startswith('# '): html.append(f'<h1 style="color:#1a1a2e">{line[2:]}</h1>')
        elif line.startswith('- ') or line.startswith('• '):
            html.append(f'<li style="margin:3px 0">{line[2:]}</li>')
        elif line.strip() == '':
            html.append('<br>')
        else:
            html.append(f'<p style="margin:4px 0;line-height:1.6">{line}</p>')
    return '\n'.join(html)


@router.post('/send-email')
def send_email(req: SendEmailRequest):
    if not settings.email_user or not settings.email_password:
        raise HTTPException(400, 'Email not configured. Please set EMAIL_USER and EMAIL_PASSWORD in .env')

    # Fetch report for attachment
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM research_reports WHERE id = ?", (req.report_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, 'Report not found')

    report = dict(row)
    symbol = report['symbol']
    date_str = report['created_at'][:10]
    report_type = 'Deep Analysis' if report['report_type'] == 'deep' else 'Quick Analysis'

    # Build HTML email
    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#222">
  <div style="background:#1a1a2e;color:white;padding:20px 24px;border-radius:8px 8px 0 0">
    <div style="font-size:20px;font-weight:bold">📊 IvyTrader · {report_type}</div>
    <div style="font-size:14px;opacity:0.7;margin-top:4px">{symbol} · {date_str}</div>
  </div>
  <div style="padding:20px 24px;background:#f9f9f9;border:1px solid #eee">
    {req.body.replace(chr(10), '<br>')}
  </div>
  <div style="padding:20px 24px;background:white;border:1px solid #eee;border-top:none">
    <div style="font-size:13px;color:#555;margin-bottom:12px">📎 Attachment: Full Research Report</div>
    {_markdown_to_html(report['content'])}
  </div>
  <div style="padding:12px 24px;background:#f0f0f0;font-size:11px;color:#999;border-radius:0 0 8px 8px">
    Sent by IvyTrader · {settings.email_from_name}
  </div>
</div>
"""

    # Build markdown attachment
    attachment_content = f"# {symbol} {report_type} — {date_str}\n\n{report['content']}"

    try:
        msg = MIMEMultipart('mixed')
        msg['From']    = f"{settings.email_from_name} <{settings.email_user}>"
        msg['To']      = ', '.join(req.to_emails)
        msg['Subject'] = req.subject

        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # Attach markdown file
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{symbol}_{date_str}_report.md"')
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(settings.email_user, settings.email_password)
            server.sendmail(settings.email_user, req.to_emails, msg.as_string())

    except Exception as e:
        raise HTTPException(500, f'Send failed: {str(e)}')

    return {'ok': True, 'sent_to': req.to_emails}


class DraftEmailRequest(BaseModel):
    report_id: str
    recipient: Optional[str] = ''

@router.post('/draft-email')
def draft_email(req: DraftEmailRequest):
    """Use AI to draft an email body for a report."""
    import anthropic
    report_id = req.report_id
    recipient = req.recipient or ''

    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM research_reports WHERE id = ?", (report_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, 'Report not found')

    report = dict(row)
    symbol   = report['symbol']
    rtype    = 'Deep Analysis (Multi-Agent)' if report['report_type'] == 'deep' else 'Quick Analysis'
    snippet  = report['content'][:1500]

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=600,
        system="You are a professional investment analyst. Always respond in English only, regardless of the language in the report content.",
        messages=[{
            'role': 'user',
            'content': f"""Write a short professional email body (3-4 paragraphs) in English to share this investment research report with a colleague.

Stock: {symbol}
Report type: {rtype}
Recipient: {recipient or 'investment team member'}
Report excerpt:
{snippet}

Requirements:
- Write in English only
- Briefly state the purpose of sharing this report
- Mention 1-2 key findings or highlights from the excerpt
- Invite the recipient to review and share their thoughts
- Close politely
- Do NOT include salutation or signature, only the body paragraphs"""
        }]
    )
    return {'body': response.content[0].text}
