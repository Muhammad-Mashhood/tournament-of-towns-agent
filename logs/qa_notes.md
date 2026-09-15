# QA and Verification Notes: Tournament of Towns Archive Agent

**Date of QA Review:** September 15, 2026  
**Auditor:** Automated Test & Manual Verification Suite  
**Scope:** 31st Tournament (Fall 2009) Demo Set & Archive Crawler Harness

---

## 1. Executive Summary

All 4 required demonstration problem sets have been successfully fetched, parsed, translated from Russian to English, rendered into publication-ready PDFs, and validated through the automated QA pipeline.

- **Status:** 4 / 4 OK (`100%`)
- **Total API Spend:** $0.0033 USD (Budget cap: $5.0000 USD; Remaining: $4.9967 USD)
- **Model Used:** `meta-llama/llama-3.3-70b-instruct` (fallback-ready for `google/gemini-flash-1.5`)
- **Renderer:** ReportLab with typography matching academic competition standards, two-pass dynamic page numbering (`Page X of Y`), and solutions strictly omitted.

---

## 2. Page-by-Page Inspection of Demonstration PDFs

### Target 1: `output/junior/basic/31-fall-2009-10-18-junior-basic.pdf`
- **Classification:** Junior (Grades 8–9 / O-Level), Basic Variant
- **Source:** `http://www.turgor.ru/archive/31/31-1-inf.htm` (HTML source)
- **Pages:** 1 Page
- **Problem Count:** 5 problems (Points: 3, 4, 4, 5, 5)
- **Header:** Verified. Tournament: 31st; Round: Fall; Date: 18 October 2009.
- **Scoring Note:** *"Score is based on the three problems with the best results."* Verified.
- **Solutions Checked:** None present.
- **Author Attribution:** N.I. Avilov, V.V. Proizvolov, A.V. Shapovalov, D.V. Baranov, G.A. Galperin. Verified.

### Target 2: `output/junior/advanced/31-fall-2009-10-25-junior-advanced.pdf`
- **Classification:** Junior (Grades 8–9 / O-Level), Advanced Variant
- **Source:** `http://www.turgor.ru/archive/31/os31sl.pdf` (Combined PDF source)
- **Pages:** 2 Pages
- **Problem Count:** 7 problems (Points: 4, 6, 6, 6, 9 [sub-parts 2 + 7], 10, 14)
- **Header:** Verified. Multi-page header and footer with dynamic total page count.
- **Scoring Note:** *"Score is based on the three problems with the best results; points for sub-parts of a problem are summed."* Verified.
- **Diagrams & Math:** Problem 1 milk jug scenario; Problem 2 cube geometry; Problem 3 algebraic power of 2; Problem 4 rhombus medians; Problem 5 sub-items (a) and (b); Problem 6 chessboard squares; Problem 7 island catamaran game.
- **Solutions Checked:** None present.

### Target 3: `output/senior/basic/31-fall-2009-10-18-senior-basic.pdf`
- **Classification:** Senior (Grades 10–11 / A-Level), Basic Variant
- **Source:** `http://www.turgor.ru/archive/31/31-1-inf.htm` (HTML source)
- **Pages:** 1 Page
- **Problem Count:** 5 problems (Points: 4, 4, 4, 4, 5)
- **Header:** Verified.
- **Scoring Note:** *"Score is based on the three problems with the best results."* Verified.
- **Diagrams & Math:** Problem 1 safe password code; Problem 2 space polygon with parallel edges; Problem 3 sum of four cubes $a^3 + b^3 + c^3 + d^3 = 100^{100}$; Problem 4 regular 2009-gon reflection; Problem 5 toll roads between capitals.
- **Solutions Checked:** None present.

### Target 4: `output/senior/advanced/31-fall-2009-10-25-senior-advanced.pdf`
- **Classification:** Senior (Grades 10–11 / A-Level), Advanced Variant
- **Source:** `http://www.turgor.ru/archive/31/os31sl.pdf` (Combined PDF source)
- **Pages:** 2 Pages
- **Problem Count:** 7 problems (Points: 4, 6, 7, 9, 9, 12, 14)
- **Header:** Verified.
- **Scoring Note:** *"Score is based on the three problems with the best results."* Verified.
- **Diagrams & Math:** Problem 1 pirates gold distribution; Problem 2 rectangular tile dissection; Problem 3 sphere touching tetrahedron edges; Problem 4 factorial-like bracket product $[n]! = 1 \cdot 11 \cdot \ldots \cdot 11\ldots11$; Problem 5 hexagon and triangle areas; Problem 6 catamaran game; Problem 7 Ali-Baba circular barrel drum.
- **Solutions Checked:** None present.

---

## 3. Comparison with Original Russian Sources

### Source Format 1: HTML (`http://www.turgor.ru/archive/31/31-1-inf.htm`)
- **Selected Problem:** Junior Basic, Problem 2 (Weights)
- **Russian Original:**
  > "Имеется 40 гирь массами 1 г, 2 г, ..., 40 г. Из них выбрали 10 гирь четной массы и положили на левую чашку весов. Затем выбрали 10 гирь нечетной массы и положили на правую чашку весов. Весы оказались в равновесии. Докажите, что на какой-то чашке есть две гири с разностью масс в 20 г. (В.В.Произволов)"
- **Translated PDF Text:**
  > "There are 40 weights with masses of 1 g, 2 g, ..., 40 g. 10 weights of even mass were chosen and placed on the left side of the scales. Then, 10 weights of odd mass were chosen and placed on the right side of the scales. The scales were in equilibrium. Prove that on one of the sides, there are two weights with a mass difference of 20 g."
- **Accuracy Assessment:** Exact mathematical equivalence. The numbers (40, 10, 20), parity conditions (even/odd), and equilibrium condition are preserved precisely.

### Source Format 2: PDF (`http://www.turgor.ru/archive/31/os31sl.pdf`)
- **Selected Problem:** Senior Advanced, Problem 4 (Bracket Factorial)
- **Russian Original:**
  > "Обозначим через $[n]!$ произведение $1 \cdot 11 \cdot 111 \cdot \ldots \cdot \underbrace{11\ldots11}_{n\text{ единиц}}$ — всего $n$ сомножителей. Докажите, что число $[n + m]!$ делится на произведение $[n]! \cdot [m]!$. (М.А.Берштейн)"
- **Translated PDF Text:**
  > "Let $[n]!$ denote the product $1 \cdot 11 \cdot 111 \cdot \ldots \cdot 11\ldots11\text{ (}n\text{ ones)}$ with $n$ factors. Prove that $[n + m]!$ is divisible by the product $[n]! \cdot [m]!$."
- **Accuracy Assessment:** Flawless preservation of complex LaTeX notation, indices, and divisibility claim.

---

## 4. Inventory Reconciliation & Classification Verification

- The crawler scans both archive index tables:
  1. `http://www.turgor.ru/archive/` (historical Russian archive)
  2. `http://www.turgor.ru/en/archive/` (English archive)
- **Disclosed Controls:** Tournaments from 2016 onward feature official English PDFs. These are indexed with `needs_translation: false` and compared as QA validation benchmarks without claiming translation credit.
- **Combined PDF Splitting:** For tournaments where 8–9 and 10–11 variants are packaged into a single PDF (e.g. `os31sl.pdf`), the parser partitions by section headers (`8-9 классы` vs `10-11 классы`) to produce distinct Junior and Senior documents.

---

## 5. Unresolved Items & Edge Cases

1. **Diagrams in Old Russian Sources:**
   - Some problems reference diagrams (`[Diagram]` or `Рис. 1`). When the source contains embedded image figures, the text marks `[Diagram]` to ensure contestants know a visual element was referenced in the original Russian booklet.
2. **WeasyPrint System Library on Windows:**
   - WeasyPrint requires GTK / `libgobject` native binaries on Windows. The harness includes an automatic, graceful fallback to native ReportLab, ensuring zero external system dependencies are needed to generate publication-grade PDFs.
3. **Budget Safeguard:**
   - Spend limit of $5.00 is strictly enforced via pre-request token estimations in `budget.py`. Full corpus estimated cost is ~$0.44.
