# Singapore Policy Analysis Guidelines

This document serves as the foundational reference for the Policy Analysis Agent. It outlines the core Singaporean insurance products, their target demographics, and the logical criteria required to accurately match a lead to a policy.

---

## 1. Integrated Shield Plan (IP) + Rider
- **Purpose/Objective**: Upgrades basic MediShield Life to cover Class A or Private Hospital wards and reduces out-of-pocket expenses via riders (covering deductibles/co-payments).
- **Target Customer Profile**: Almost all Singaporeans/PRs, but especially those without existing private health cover who value comfort and faster healthcare access.
- **Key Customer Attributes/Criteria**: `Existing Cover = 0 or low`, `Age = Any`.
- **How the Policy Aligns**: Addresses the "protection gap" where MediShield Life only covers B2/C wards in public hospitals. It appeals to the practical desire not to wipe out MediSave for major surgeries.
- **Recommendation Logic**: `IF Existing Health Cover < S$50,000 OR is missing THEN Recommend IP + Rider.` (Serves as the baseline/default recommendation).
- **Example Scenario**: A 28-year-old administrative worker earning S$45,000/year with no existing coverage. The agent recommends an IP to establish baseline private healthcare access before any pre-existing conditions develop.

---

## 2. Whole Life with Early Critical Illness (ECI) Rider
- **Purpose/Objective**: Provides lifelong death/Total Permanent Disability (TPD) coverage and payouts for early-stage critical illnesses (e.g., early-stage cancer), ensuring income replacement during recovery.
- **Target Customer Profile**: Married individuals, parents, or those with higher health risks (e.g., smokers) who have housing loans or dependents relying on their income.
- **Key Customer Attributes/Criteria**: `Marital Status = Married` OR `Dependents > 0` OR `Tobacco Use = Y`.
- **How the Policy Aligns**: Protects the family from inheriting massive liabilities (like an HDB mortgage) and provides a cash buffer if they must stop working due to early-stage illness. 
- **Recommendation Logic**: `IF (Dependents > 0 OR Marital Status = Married) AND Tobacco Use = Y THEN Recommend Whole Life + ECI.` (High priority for smokers with dependents).
- **Example Scenario**: A 40-year-old smoker with 2 children. The agent recommends this to protect the family from the elevated risk of critical illness and ensure the children's lifestyle isn't compromised.

---

## 3. Term Life to Age 65
- **Purpose/Objective**: Pure protection plan offering a massive payout for death/TPD at a very low premium, covering the individual during their active working and mortgage-paying years.
- **Target Customer Profile**: Budget-conscious young families, sole breadwinners, or individuals heavily invested in housing (BTO/Condo) who need high coverage but cannot afford Whole Life premiums.
- **Key Customer Attributes/Criteria**: `Age < 45`, `Income < S$60,000`, `Recent Life Event = Home loan or Marriage`.
- **How the Policy Aligns**: Provides maximum protection for the lowest cost precisely when liabilities (mortgage, young kids) are highest. Coverage ends at 65 when the house is ideally paid off and CPF Life kicks in.
- **Recommendation Logic**: `IF Recent Life Event IN ("Home loan", "Marriage") AND Income < S$60,000 THEN Recommend Term Life to 65.`
- **Example Scenario**: A 32-year-old newlywed earning S$55,000/year who just took out an HDB home loan. They need S$500k coverage purely to cover the debt if tragedy strikes.

---

## 4. Investment-Linked Policy (ILP)
- **Purpose/Objective**: A hybrid policy offering both life insurance protection and wealth accumulation by investing premiums into curated sub-funds.
- **Target Customer Profile**: Younger, high-income professionals who have excess cash flow, maxed out their CPF Special Account (SA), and want aggressive wealth accumulation that outpaces inflation.
- **Key Customer Attributes/Criteria**: `Age < 35`, `Income > S$80,000`, `Existing Cover = High`.
- **How the Policy Aligns**: Capitalizes on their long investment horizon and high risk tolerance. It appeals to the "kiasu" mindset of maximizing wealth while remaining protected.
- **Recommendation Logic**: `IF Age < 35 AND Income > S$80,000 THEN Recommend Investment-Linked Policy (ILP).`
- **Example Scenario**: A 30-year-old tech executive earning S$120,000/year who already has an IP. They want to invest their disposable income to retire early, making an ILP the perfect fit.

---

## 5. Personal Accident (PA) & Disability Income Insurance
- **Purpose/Objective**: Pays out for accidental injuries, medical reimbursement (e.g., TCM, physiotherapy), and replaces up to 75% of monthly income if unable to work due to accident/illness.
- **Target Customer Profile**: Active individuals, gig economy workers (Grab drivers, freelancers), or those engaged in high-risk hobbies.
- **Key Customer Attributes/Criteria**: `Hobbies INCLUDE (cycling, rock climbing, diving, racing, etc.)` OR `Occupation = Gig/Manual Labour`.
- **How the Policy Aligns**: Fills the gap left by MediShield Life, which covers hospital bills but *not* outpatient accident treatments or the loss of daily income.
- **Recommendation Logic**: `IF Hobbies overlap with high-risk activities OR Occupation indicates gig-economy THEN Recommend PA & Disability Income.`
- **Example Scenario**: A 26-year-old freelance graphic designer whose hobby is mountain biking. If they break an arm and cannot work for two months, this policy covers their lost income.

---

## 6. CareShield Life Supplement
- **Purpose/Objective**: Enhances the mandatory government CareShield Life scheme (which pays out ~S$600/month for severe disability) to provide a higher monthly payout and lower the threshold for claims.
- **Target Customer Profile**: Middle-aged individuals approaching their senior years who are concerned about the high costs of long-term care, nursing homes, or domestic helpers in Singapore.
- **Key Customer Attributes/Criteria**: `Age >= 40`.
- **How the Policy Aligns**: S$600/month from basic CareShield is rarely enough to hire a foreign domestic worker or pay for a nursing facility in Singapore. The supplement ensures they don't become a burden to their children.
- **Recommendation Logic**: `IF Age >= 40 AND Income > S$50,000 THEN Recommend CareShield Life Supplement.`
- **Example Scenario**: A 45-year-old manager earning S$90,000/year. They are acutely aware of the costs of eldercare and want to lock in a S$2,000/month payout for severe disability to protect their retirement nest egg.

---

## 7. Maternity & Child Education Endowment
- **Purpose/Objective**: Provides pregnancy complication cover for the mother and congenital illness cover for the newborn, later transitioning into an endowment plan to fund university tuition.
- **Target Customer Profile**: Expectant parents or families who recently welcomed a new child.
- **Key Customer Attributes/Criteria**: `Recent Life Event = New child` OR `Dependents recently increased`.
- **How the Policy Aligns**: Taps directly into the Singaporean priority of ensuring top-tier education for children while hedging against early medical complications.
- **Recommendation Logic**: `IF Recent Life Event = "New child" THEN Recommend Maternity & Child Education Endowment.`
- **Example Scenario**: A 34-year-old couple expecting their first baby. They purchase this policy to cover the pregnancy and begin aggressively compounding returns to pay for the child's future local/overseas university fees.
