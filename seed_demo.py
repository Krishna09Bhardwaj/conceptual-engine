from datetime import datetime, timedelta
from database import create_client, add_data_entry, add_action_item, create_user, is_users_empty
from vector_store import add_to_vector_store
from auth import hash_password


def seed_users():
    if not is_users_empty():
        return
    users = [
        ("admin",    "Admin",         "admin"),
        ("tulsi",    "Tulsi Rani",    "pm"),
        ("dhruv",    "Dhruv Chopra",  "pm"),
        ("lakshita", "Lakshita Saini","pm"),
    ]
    passwords = {
        "admin":    "admin123",
        "tulsi":    "tulsi123",
        "dhruv":    "dhruv123",
        "lakshita": "lakshita123",
    }
    for username, name, role in users:
        create_user(username, name, role, hash_password(passwords[username]))


def seed():
    today = datetime.utcnow()

    # ── Client 1: Arjun Mehta — O-1A, AT RISK ────────────────────────────────
    deadline_arjun = (today + timedelta(days=45)).strftime("%Y-%m-%d")
    arjun_id = create_client(
        name="Arjun Mehta",
        case_type="O-1A",
        deadline=deadline_arjun,
        assigned_pm="Tulsi Rani",
        status="At Risk",
        risk_flag=1,
        notes="Extraordinary ability petition. Published researcher with 3 patents. Recommendation letters from key industry experts are the main bottleneck.",
    )

    arjun_whatsapp = """WhatsApp conversation for Arjun Mehta:
[04/01/25 09:15:22] Arjun Mehta: Hi Tulsi, any update on the recommendation letters?
[04/01/25 09:17:05] Tulsi Rani: Hi Arjun! I've sent reminders to Prof. Sharma and Dr. Williams. Prof. Sharma confirmed he'll send by April 10.
[04/01/25 09:18:30] Arjun Mehta: What about Dr. Williams? He hasn't replied to my emails either.
[04/01/25 09:19:45] Tulsi Rani: Dr. Williams is at a conference till April 8. I'll follow up directly with his assistant on April 9. Don't worry.
[04/05/25 14:22:10] Arjun Mehta: Tulsi I'm worried, the deadline is getting close. We still need 3 more letters.
[04/05/25 14:25:33] Tulsi Rani: Yes I know. We have confirmed letters from Prof. Sharma, Dr. Kapoor, and Dr. Iyer. We still need Dr. Williams, Prof. Chen, and one more from your employer.
[04/05/25 14:26:50] Arjun Mehta: My employer's legal team is slow. They want to review the letter template before signing off.
[04/05/25 14:28:00] Tulsi Rani: I'll send the template to their legal team today. Can you connect me with your HR contact?
[04/07/25 11:00:00] Arjun Mehta: HR contact is Sarah Johnson, sjohnson@techcorp.com. She handles all external legal communications.
[04/07/25 11:05:22] Tulsi Rani: Got it! Emailing Sarah now with the template. Also just heard from Dr. Williams - he said he will send the letter by April 15th.
[04/10/25 16:30:00] Arjun Mehta: Prof. Sharma's letter came in! Very strong, mentions the three patents specifically.
[04/10/25 16:32:44] Tulsi Rani: Excellent! That's a great letter. We now have 4 confirmed and need 2 more. Prof. Chen is still pending.
[04/12/25 09:00:00] Arjun Mehta: Prof. Chen said she needs another week. She's very busy with end of semester.
[04/12/25 09:03:00] Tulsi Rani: OK. That takes us to April 19th for Prof. Chen. Combined with April 15th for Dr. Williams, we should have all 6 letters by April 20th. The petition filing deadline is May 10th. We are tight but doable IF no more delays.
[04/15/25 10:00:00] Arjun Mehta: Any news from Dr. Williams?
[04/15/25 10:05:00] Tulsi Rani: Not yet today. I'll call his office this afternoon. Also, did you get the draft petition to review?
[04/15/25 10:07:00] Arjun Mehta: Yes, reviewing it now. Found a few dates that are wrong in the publication list. Will send corrections tonight.
[04/15/25 18:00:00] Arjun Mehta: Sent the corrections. 3 publication dates were wrong and one patent number was listed twice.
[04/16/25 08:30:00] Tulsi Rani: Got it, fixing now. This is critical - thank you for catching that. Also still waiting on Dr. Williams. I flagged this case as AT RISK internally."""

    entry_id = add_data_entry(arjun_id, "whatsapp", arjun_whatsapp)
    add_to_vector_store(arjun_id, "Arjun Mehta", "whatsapp", arjun_whatsapp, entry_id)

    arjun_transcript = """Fathom call transcript — Strategy Call with Arjun Mehta (April 8, 2025):

Tulsi Rani: Hi Arjun, thanks for jumping on this call. I wanted to walk through where we are on the petition.

Arjun Mehta: Of course. I'm getting nervous. The filing window is closing.

Tulsi Rani: Completely understandable. Let me give you the full picture. For the O-1A, we need to satisfy at least 3 out of 8 criteria. You currently meet: original scientific contribution, published scholarly articles, high salary relative to others in your field, and judging others' work. That's 4 criteria which is strong.

Arjun Mehta: What about the patents? I have 3 US patents.

Tulsi Rani: Yes, the patents strengthen the original contribution criterion significantly. Prof. Sharma's letter specifically addresses this and it's very compelling. The weak point right now is getting all 6 recommendation letters before April 20th.

Arjun Mehta: What happens if we don't get all of them in time?

Tulsi Rani: We could file with 4 or 5 letters, but 6 is stronger and USCIS might send an RFE asking for more evidence. I'd rather file complete. Dr. Williams is the most critical letter because he's a direct collaborator on your most-cited paper.

Arjun Mehta: Okay. I can also ask Dr. Patel from Stanford - he reviewed my patent applications and wrote me a reference for my current job.

Tulsi Rani: That's perfect! Dr. Patel from Stanford would be an excellent additional letter. He would be letter number 7 if needed. Let's add him as a backup. Can you reach out to him today?

Arjun Mehta: Yes, I'll email him right after this call.

Tulsi Rani: Great. Also - please complete the review of the draft petition by April 16th. We need the corrected version back so we can do a final review before filing.

Arjun Mehta: I'll prioritize it. One more thing - my I-94 expires May 28th. Does that affect the filing?

Tulsi Rani: Great catch. Since we're filing an O-1A change of status petition, we need to file at least 10 days before your I-94 expires to maintain status. May 28th minus 10 days is May 18th. We have a filing deadline of May 10th anyway. We're fine but I'm flagging it so we do not miss it.

Arjun Mehta: Thank you Tulsi. I feel better now. Let me get on those action items.

Tulsi Rani: Perfect. Summary of what we need: 1) Reach out to Dr. Patel today, 2) Return petition corrections by April 16th, 3) Follow up with Prof. Chen, 4) Confirm receipt from Dr. Williams. I'll keep escalating on my end. We'll schedule a check-in call for April 22nd."""

    entry_id2 = add_data_entry(arjun_id, "fathom", arjun_transcript, source_url="https://fathom.video/demo-arjun-strategy-call")
    add_to_vector_store(arjun_id, "Arjun Mehta", "fathom", arjun_transcript, entry_id2)

    arjun_email = """Email — April 17, 2025 — from Tulsi Rani to Arjun Mehta:

Subject: Status Update — O-1A Petition — Action Required

Hi Arjun,

Quick update on where we stand:

LETTERS STATUS:
✅ Prof. Sharma (IIT Delhi) — Received, excellent letter
✅ Dr. Kapoor (MIT) — Received
✅ Dr. Iyer (Google Research) — Received
⏳ Dr. Williams (Stanford) — Expected April 15, still pending as of today April 17
⏳ Prof. Chen (CMU) — Expected April 19
✅ Dr. Patel (Stanford) — Confirmed, sending by April 18

That gives us 4 confirmed, 2 pending. Best case: all 6 in by April 20.

PETITION DRAFT:
- Your corrections received, incorporated.
- Petition is 98% complete.
- Final review needed once all letters are in.

RISK ITEMS:
1. Dr. Williams — 2 days overdue. I'm calling his office this afternoon.
2. If we don't receive by April 22nd, we may need to file without and risk RFE.
3. I-94 expires May 28th — we MUST file by May 10th regardless.

NEXT STEPS FOR YOU:
- Confirm Dr. Patel's letter is submitted
- No further action needed on your end — I'll handle all follow-ups

I'll update you by end of business today.

Best,
Tulsi Rani
Program Manager, JineeGreenCard"""

    entry_id3 = add_data_entry(arjun_id, "email", arjun_email)
    add_to_vector_store(arjun_id, "Arjun Mehta", "email", arjun_email, entry_id3)

    add_action_item(arjun_id, "Follow up with Dr. Williams — letter overdue since April 15", assigned_to="Tulsi Rani", due_date=(today + timedelta(days=2)).strftime("%Y-%m-%d"))
    add_action_item(arjun_id, "Confirm Prof. Chen submits letter by April 19", assigned_to="Tulsi Rani")
    add_action_item(arjun_id, "Complete final review of petition draft once all letters received", assigned_to="Tulsi Rani")
    add_action_item(arjun_id, "File petition by May 10th — I-94 expires May 28th", assigned_to="Tulsi Rani", due_date=(today + timedelta(days=16)).strftime("%Y-%m-%d"))
    add_action_item(arjun_id, "Verify Dr. Patel letter submitted to JineeGreenCard portal", assigned_to="Arjun Mehta")

    # ── Client 2: Priya Sharma — EB-1A, Active ────────────────────────────────
    deadline_priya = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    priya_id = create_client(
        name="Priya Sharma",
        case_type="EB-1A",
        deadline=deadline_priya,
        assigned_pm="Dhruv Chopra",
        status="Active",
        risk_flag=0,
        notes="EB-1A Green Card petition. Software engineering leader with multiple publications and conference talks. Currently responding to RFE on national importance criterion.",
    )

    priya_whatsapp = """WhatsApp conversation for Priya Sharma:
[03/20/25 10:00:00] Priya Sharma: Dhruv, I received an RFE from USCIS. What does this mean for my timeline?
[03/20/25 10:05:00] Dhruv Chopra: Hi Priya, an RFE (Request for Evidence) is common - don't panic. We have 87 days to respond. Let me review the exact items they're asking for.
[03/20/25 10:10:00] Dhruv Chopra: Okay I reviewed it. USCIS wants more evidence on two criteria: 1) Critical role in distinguished organizations 2) Original contribution of major significance
[03/20/25 10:15:00] Priya Sharma: What do I need to do?
[03/20/25 10:18:00] Dhruv Chopra: We need to get letters from your current employer (Google) specifically addressing your critical role, and also citations data for your research papers. Do you have access to Google Scholar citations count?
[03/21/25 09:00:00] Priya Sharma: Yes, my most cited paper has 342 citations. Second has 187. I'll screenshot from Google Scholar.
[03/21/25 09:05:00] Dhruv Chopra: 342 citations is very strong for CS field. That alone addresses the original contribution criterion.
[03/25/25 14:00:00] Priya Sharma: I talked to my manager Rajesh. He's willing to write a strong letter about my role leading the ML infrastructure team that serves 2 billion users.
[03/25/25 14:10:00] Dhruv Chopra: That is excellent. "2 billion users" is exactly the kind of scale that proves critical role. Draft letter template sent to your email.
[04/01/25 11:00:00] Priya Sharma: Tax returns question - I need 2022 and 2023 right? Or just 2023?
[04/01/25 11:05:00] Dhruv Chopra: We need 2022 and 2023 tax returns for the high salary criterion evidence. Also W-2s for both years.
[04/01/25 11:10:00] Priya Sharma: Got them. Uploading to the portal now.
[04/05/25 16:00:00] Dhruv Chopra: Tax returns received! Looks good. One question - your 2022 return shows employment at Meta before Google. Is that correct?
[04/05/25 16:15:00] Priya Sharma: Yes, I joined Google in January 2023. Meta before that.
[04/08/25 09:00:00] Dhruv Chopra: RFE response is 80% complete. Waiting on: Google employer letter and expert opinion letter from Dr. Martinez at Berkeley who agreed to write one.
[04/10/25 10:00:00] Priya Sharma: Rajesh submitted the employer letter! I reviewed it, it's very strong.
[04/10/25 10:10:00] Dhruv Chopra: Perfect! Now just waiting on Dr. Martinez's expert opinion letter. Do you have an ETA from him?
[04/12/25 15:00:00] Priya Sharma: Dr. Martinez said he needs 2 more weeks. April 26th.
[04/12/25 15:05:00] Dhruv Chopra: That works perfectly. RFE deadline is June 15th. We'll submit the complete response by May 15th to be safe."""

    entry_id4 = add_data_entry(priya_id, "whatsapp", priya_whatsapp)
    add_to_vector_store(priya_id, "Priya Sharma", "whatsapp", priya_whatsapp, entry_id4)

    priya_note = """Case notes — Priya Sharma EB-1A:

RFE received March 20, 2025. Response deadline June 15, 2025.

Evidence collected so far:
- Google Scholar citations: 342 (main paper), 187, 94, 73 — total 700+ citations
- Tax returns 2022 and 2023 uploaded ✓
- W-2s both years uploaded ✓
- Employer letter from Google (Rajesh Kumar, Engineering Director) — received April 10 ✓
- Conference talks: Speaker at NeurIPS 2023, ICML 2022 — evidence prepared ✓
- Publication list: 8 peer-reviewed papers, 3 conference papers

Still pending:
- Expert opinion letter from Dr. Elena Martinez (UC Berkeley) — expected April 26th
- Final compilation and legal review of RFE response

High salary criterion: Priya's TC at Google is $485,000. BLS data for software engineers shows 90th percentile at $208,000. She is at 233% of 90th percentile. Strong evidence.

Overall assessment: RFE response will be strong. No significant risks identified. Timeline comfortable."""

    entry_id5 = add_data_entry(priya_id, "note", priya_note)
    add_to_vector_store(priya_id, "Priya Sharma", "note", priya_note, entry_id5)

    add_action_item(priya_id, "Collect expert opinion letter from Dr. Martinez (expected April 26)", assigned_to="Dhruv Chopra", due_date=(today + timedelta(days=12)).strftime("%Y-%m-%d"))
    add_action_item(priya_id, "Compile and submit complete RFE response by May 15th", assigned_to="Dhruv Chopra", due_date=(today + timedelta(days=21)).strftime("%Y-%m-%d"))

    # ── Client 3: Rohit Verma — H-1B, Active ─────────────────────────────────
    deadline_rohit = (today + timedelta(days=120)).strftime("%Y-%m-%d")
    rohit_id = create_client(
        name="Rohit Verma",
        case_type="H-1B",
        deadline=deadline_rohit,
        assigned_pm="Lakshita Saini",
        status="Active",
        risk_flag=0,
        notes="H-1B cap-subject petition. Software engineer at DataBridge Inc. April lottery registration completed. Awaiting selection results.",
    )

    rohit_note = """Case notes — Rohit Verma H-1B:

H-1B cap-subject petition for FY2026.

Timeline:
- USCIS registration period: March 1-18, 2025 — completed ✓
- Registration submitted for Rohit on March 10, 2025 ✓
- Lottery selection results expected: Late March to early April 2025
- If selected: I-129 petition must be filed by June 30, 2025

Current status: WAITING FOR LOTTERY SELECTION RESULT

Employer details:
- Company: DataBridge Inc., San Jose, CA
- Position: Senior Software Engineer
- Salary: $145,000/year (prevailing wage confirmed LCA filed)
- Attorney of record: JineeGreenCard

Documents ready if selected:
- LCA (Labor Condition Application) — approved ✓
- Educational credentials evaluation — NACES approved evaluation ✓
- Employer support letter — drafted, awaiting final signature
- I-129 petition — 90% complete, pending lottery selection

Risk assessment: LOW. Standard H-1B case. Main risk is lottery — purely statistical at ~30% selection rate.

Note from Lakshita: Client is aware of lottery odds. Has backup plan (L-1 if company establishes operations in Canada). Will not need L-1 if selected."""

    entry_id6 = add_data_entry(rohit_id, "note", rohit_note)
    add_to_vector_store(rohit_id, "Rohit Verma", "note", rohit_note, entry_id6)

    rohit_whatsapp = """WhatsApp conversation for Rohit Verma:
[03/10/25 11:00:00] Lakshita Saini: Hi Rohit! Confirmed — your H-1B registration was submitted to USCIS today, March 10. Registration ID: JGCR-2025-RV-4821
[03/10/25 11:15:00] Rohit Verma: Great! What are the next steps?
[03/10/25 11:20:00] Lakshita Saini: We wait for USCIS lottery results in late March / early April. If selected, we have until June 30 to file the full I-129 petition. We've already done most of the prep work so we'll be ready quickly.
[03/10/25 11:25:00] Rohit Verma: What are my chances?
[03/10/25 11:30:00] Lakshita Saini: Historically around 25-35% selection rate. We've done everything we can to maximize the registration. The rest is up to the lottery. I'll notify you immediately when results are out.
[04/01/25 09:00:00] Rohit Verma: Any news on lottery results?
[04/01/25 09:05:00] Lakshita Saini: Not yet. USCIS says notifications going out in waves through early April. Keep checking your email! I'll also monitor and alert you.
[04/08/25 14:00:00] Lakshita Saini: Hi Rohit! GREAT NEWS - you've been SELECTED in the H-1B lottery! Congratulations! 🎉
[04/08/25 14:02:00] Rohit Verma: Oh wow!! That's amazing! What happens now?
[04/08/25 14:05:00] Lakshita Saini: Now we have until June 30, 2025 to file the full I-129 petition. I'll schedule a call this week to walk through the remaining documents we need from you.
[04/10/25 15:00:00] Lakshita Saini: Documents still needed from you: 1) Signed employer support letter (I'll send for signature), 2) Copy of your degree certificate, 3) Last 3 pay stubs from current employer
[04/10/25 15:10:00] Rohit Verma: I'll gather everything this week. My employer is TechStart Inc. Should that be on the letter?
[04/10/25 15:12:00] Lakshita Saini: Wait - your new H-1B sponsor is DataBridge Inc. correct? Or TechStart? Let me double-check our records.
[04/10/25 15:15:00] Rohit Verma: Sorry yes - DataBridge Inc is the sponsoring company. TechStart is my current employer that I'm leaving.
[04/10/25 15:17:00] Lakshita Saini: Got it - confirmed DataBridge. All documents in our file show DataBridge. Please get those documents to us by April 20th so we have time for review before June 30 deadline."""

    entry_id7 = add_data_entry(rohit_id, "whatsapp", rohit_whatsapp)
    add_to_vector_store(rohit_id, "Rohit Verma", "whatsapp", rohit_whatsapp, entry_id7)

    add_action_item(rohit_id, "Collect signed employer support letter from DataBridge Inc.", assigned_to="Lakshita Saini", due_date=(today + timedelta(days=6)).strftime("%Y-%m-%d"))
    add_action_item(rohit_id, "Receive degree certificate copy and 3 pay stubs from Rohit", assigned_to="Lakshita Saini", due_date=(today + timedelta(days=6)).strftime("%Y-%m-%d"))
    add_action_item(rohit_id, "File complete I-129 H-1B petition — deadline June 30, 2025", assigned_to="Lakshita Saini", due_date=(today + timedelta(days=67)).strftime("%Y-%m-%d"))
