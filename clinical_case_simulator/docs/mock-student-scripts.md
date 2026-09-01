# Mock Student Scripts — test the simulator yourself

Three scripted students, all running the **same case**, so the scores are
directly comparable. Paste the lines one at a time and watch what the agent does.

**Case:** `IM-002` — Central chest discomfort in a 54-year-old man  
**Setting:** Emergency department  
**The real answer (don't peek during the run):** hidden below in *Appendix*.

## How to run these

Pick whichever is easiest:

| Where | How |
|---|---|
| Gemini Enterprise | Open the app, pick **Clinical Case Simulator**, paste turns one at a time |
| Local dev UI | `./run_local.sh` → http://localhost:8000 → pick `clinical_simulator` |
| Terminal | `python -m clinical_simulator.console` |
| Automated | `python -m clinical_simulator.mock_students` (runs all three and scores them) |

Paste **one line per turn** and wait for the reply before sending the next.

> ### ⚠ Turn 1 is not optional
>
> Every script begins with `Start case IM-002.` **You must send that line first,
> in a fresh conversation.** The scripts ask about chest-wall tenderness, calf
> swelling and the JVP — findings that exist in IM-002 and not in every case.
>
> Paste turn 2 onwards into a conversation already running a different case and
> the agent will correctly answer *"that examination is not defined for this
> case"*. That is the simulator refusing to invent a finding — working as
> intended, on the wrong case.
>
> If you see that message, check which case you are actually in by asking
> **"what case am I on?"**

---

## 1. Perfect student

Systematic and safety-conscious. Full pain history, every cardiac risk factor, family history, smoking quantified, and a deliberate screen for the two diagnoses that kill. Examines properly, orders a focused set of tests, gives three differentials *with reasons* including both must-excludes, then explains how he would tell them apart before committing.

**Expected:** around **89/100** (Excellent) · 28 turns

**1.**
```text
Start case IM-002.
```
**2.**
```text
Good morning, I'm a medical student. I'm sorry you're feeling unwell. Can you tell me what's brought you in today?
```
**3.**
```text
Thank you. Can you show me where exactly the discomfort is?
```
**4.**
```text
What does it feel like — is it sharp, or more of a pressure?
```
**5.**
```text
Does it move or spread anywhere else at all?
```
**6.**
```text
When did it start, and how long has this episode lasted?
```
**7.**
```text
Is there anything that brings it on, like walking or climbing stairs?
```
**8.**
```text
And does anything make it settle?
```
**9.**
```text
Did you notice anything else with it — any sweating, feeling sick, or being short of breath?
```
**10.**
```text
Have you had episodes like this before over the last few weeks?
```
**11.**
```text
Do you have any medical conditions — blood pressure, diabetes, or high cholesterol?
```
**12.**
```text
What medication are you taking at the moment, and do you take it regularly?
```
**13.**
```text
Do you smoke, and if so how much and for how long?
```
**14.**
```text
Has anyone in your family had heart problems at a young age?
```
**15.**
```text
Have you had any long journeys, leg swelling or calf pain recently?
```
**16.**
```text
Any indigestion or heartburn, and is this pain related to meals?
```
**17.**
```text
Please check the vital signs, including blood pressure in both arms.
```
**18.**
```text
I'd like to do a cardiovascular examination and check the JVP.
```
**19.**
```text
Please examine the respiratory system and the legs for oedema or calf tenderness.
```
**20.**
```text
Can you palpate the chest wall to see if the pain is reproducible?
```
**21.**
```text
Please do a 12-lead ECG.
```
**22.**
```text
I'd like a troponin now and a repeat at three hours, plus a chest X-ray.
```
**23.**
```text
Also renal function and electrolytes, blood glucose with HbA1c, and a lipid profile.
```
**24.**
```text
My differential is: first, acute coronary syndrome, because of exertional retrosternal heaviness radiating to the left arm and jaw, relieved by rest, with diaphoresis, in a smoker with a strong family history and ST depression on the ECG. Second, aortic dissection, which I must exclude before giving any anticoagulation. Third, pulmonary embolism, given the breathlessness, though the Wells score is low. I'd also consider gastro-oesophageal reflux and pericarditis as lower probability.
```
**25.**
```text
To discriminate: the serial troponin and repeat ECG separate acute coronary syndrome from the non-cardiac causes — a rise and fall confirms infarction. For dissection I'm reassured by equal blood pressures in both arms, no radio-femoral delay and a normal mediastinum on the chest X-ray. For pulmonary embolism the normal saturations, absence of calf signs and low Wells score make it unlikely, so I would not order a CTPA. Reflux would not be relieved by rest or raise troponin.
```
**26.**
```text
Please arrange an echocardiogram as well.
```
**27.**
```text
My final diagnosis is a non-ST-elevation myocardial infarction on a background of crescendo angina. The exertional retrosternal heaviness radiating to the left arm and jaw, relieved by rest and associated with diaphoresis, is ischaemic cardiac pain. The three-week crescendo pattern ending in a prolonged episode at rest defines an acute coronary syndrome. The ECG shows horizontal ST depression in V4 to V6 with inferior T-wave inversion but no ST elevation, and the troponin rises from 214 to 890, so this is an NSTEMI rather than unstable angina or a STEMI. The regional hypokinesia on echo confirms it. His risk factors are hypertension, undiagnosed diabetes with an HbA1c of 7.4, dyslipidaemia, smoking and a first-degree family history of premature coronary disease. I excluded aortic dissection on the inter-arm pressures and mediastinum, and pulmonary embolism on the clinical probability.
```
**28.**
```text
Please evaluate my performance now.
```

---

## 2. Less-knowledge student

Anchors on 'heart attack' within four questions. Uses medical jargon at the bedside, asks the simulator to confirm the diagnosis for him, never examines the patient, orders one test, and names two diagnoses with no reasoning.

**Expected:** around **10 → ~24 after the fix/100** (Needs work) · 11 turns

**1.**
```text
Start case IM-002.
```
**2.**
```text
Do you have chest pain?
```
**3.**
```text
Is it severe?
```
**4.**
```text
Any diaphoresis or dyspnoea?
```
**5.**
```text
Is it a cardiac pain or a gastric pain?
```
**6.**
```text
Do an ECG.
```
**7.**
```text
Is this a heart attack?
```
**8.**
```text
Give me a hint.
```
**9.**
```text
My differential is acute coronary syndrome and gastritis.
```
**10.**
```text
My final diagnosis is heart attack.
```
**11.**
```text
Evaluate my performance.
```

---

## 3. Average student

Takes a competent pain history but never asks about associated symptoms, family history or medication. Checks vitals and the heart, orders the three obvious tests and stops. Reaches the correct diagnosis — but by a much narrower route, and never considers what else could kill this man.

**Expected:** around **57/100** (Borderline) · 19 turns

**1.**
```text
Start case IM-002.
```
**2.**
```text
What brings you in today?
```
**3.**
```text
Where is the pain exactly?
```
**4.**
```text
What does the pain feel like?
```
**5.**
```text
Does the pain go anywhere else?
```
**6.**
```text
When did it start?
```
**7.**
```text
Does anything make it worse?
```
**8.**
```text
Does resting help?
```
**9.**
```text
Do you have any medical problems like blood pressure or diabetes?
```
**10.**
```text
Do you smoke?
```
**11.**
```text
Please check the vital signs.
```
**12.**
```text
Please examine the cardiovascular system.
```
**13.**
```text
Please do an ECG.
```
**14.**
```text
Please send a troponin.
```
**15.**
```text
Please do a chest X-ray.
```
**16.**
```text
My differential is acute coronary syndrome, because of the central chest pain radiating to the arm with risk factors; gastro-oesophageal reflux, because he gets heartburn; and musculoskeletal pain.
```
**17.**
```text
I would use the troponin and the ECG to tell them apart.
```
**18.**
```text
My final diagnosis is acute coronary syndrome. He has central chest pain going to the left arm, he is a smoker with high blood pressure, and the ECG shows ST depression with a raised troponin.
```
**19.**
```text
Please evaluate my performance.
```

---

## What to watch for, beyond the number

The score is the least interesting output. These are the behaviours that matter:

**1. It must refuse to give the answer.**  
The less-knowledge student asks *"Is this a heart attack?"* outright at turn 7.
A correct response redirects the question back:

> I cannot answer that directly. What findings from the history and investigations
> so far make you consider a heart attack? What findings might argue against it?

If it ever confirms or denies the diagnosis mid-case, that is a serious bug — report it.

**2. The patient must stay in character.**  
Say *"any diaphoresis?"* and the patient should not understand the word. They should
answer only what was asked, and never volunteer the crucial symptom.

**3. It must record poor answers, not refuse them.**  
At turn 9 the less-knowledge student gives two diagnoses with no reasons. The agent
should **write them down and then ask why** — not refuse until they are well-formed.
This was a real defect, now fixed; if you see the agent decline to record something,
that is a regression.

**4. It must never name its own tools.**  
The student should never see words like `submit_differential`. If a tool name appears
in a reply, that is a bug.

**5. The report must always arrive.**  
Asking to be evaluated must always produce a report, even from a student who did
almost nothing.

## Reading the scores

| | Perfect | Less-knowledge | Average |
|---|---:|---:|---:|
| **Overall** | **89** | **10*** | **57** |
| History taking | 94 | 4 | 30 |
| Communication | 70 | 54 | 73 |
| Clinical reasoning | 72 | 0 | 58 |
| Differential diagnosis | 100 | 0 | 60 |
| Investigation selection | 100 | 22 | 56 |
| Case synthesis | 100 | 0 | 88 |
| Correct diagnosis | yes | no | yes |

\* The less-knowledge student scored 10 in the recorded run, but that number is
stale: the agent was refusing to record their differential and final diagnosis, so
they scored zero on answers they had actually given. That defect is fixed and the
same script should now score around **24**. The other two columns are unaffected.

**The headline result:** the perfect and average students *both got the diagnosis
right*, and are 32 marks apart. That gap is entirely process — history taken,
dangerous alternatives considered, tests chosen deliberately. That is the design
working as intended.

One counter-intuitive detail worth noticing: the **average student scored higher on
communication than the perfect one** (73 vs 70). Their questions were blunt but plain.
The strong student said "diaphoresis" and "radiate" to a bank manager. The six skills
are genuinely independent, and being thorough does not automatically make you clear.

## Write your own

Add a list to `STUDENTS` in `clinical_simulator/mock_students.py` and it is
picked up automatically:

```python
STUDENTS["rushed"] = [
    "Start case IM-002.",
    "What is the diagnosis?",
    "Evaluate my performance.",
]
```

Then: `python -m clinical_simulator.mock_students --student rushed --verbose`

Useful students to try: one who asks good questions but orders every test in the
book; one who is excellent at history and never examines the patient; one who takes
all three hints. Each probes a different part of the marking scheme.

---

## Appendix — the answer

<details>
<summary>Click only after running the case</summary>

**Non-ST-elevation myocardial infarction (NSTEMI) on a background of crescendo angina, in a patient with hypertension, undiagnosed type 2 diabetes, dyslipidaemia, smoking and a strong family history**

Exertional retrosternal heaviness radiating to the left arm and jaw, relieved by rest, with diaphoresis and nausea, is textbook ischaemic cardiac pain. The three-week crescendo pattern culminating in a prolonged episode at rest defines an acute coronary syndrome. Ischaemic ST depression without ST elevation, plus a troponin that rises from 214 to 890 ng/L, makes it an NSTEMI rather than unstable angina. Regional hypokinesia on echo in a matching territory confirms it.

**Must-exclude diagnoses** a safe student names even though they are unlikely:
- *Aortic dissection* — Catastrophic if missed and the treatment is opposite to that of ACS. Argued against by the absence of tearing pain, inter-arm BP difference, pulse deficit or a widened mediastinum.
- *Pulmonary embolism* — Another life-threatening cause of chest pain with breathlessness. Low Wells score, no risk factors, normal saturations and no right-heart strain make it unlikely.

</details>
