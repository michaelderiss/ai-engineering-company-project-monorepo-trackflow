CURRENT COMPANY BRIEFING:
{
# BRIEFING — TrackFlow

## Time series forecasting model for sales prediction

---

### 1. Why this matters to TrackFlow

Thomas (CEO) needs to know whether it's feasible to predict revenue volume for the coming months before investing in a full executive dashboard. TrackFlow bills mainly on shipment volume managed for e-commerce brands, and that volume has sharp peaks and valleys driven by the e-commerce calendar — something Ana (Warehouse) and Carlos (Carriers) already anticipate manually every year.

---

### 2. Data structure

The monthly consolidated revenue dataset for TrackFlow is already included in your monorepo, at `data/raw/trackflow_sales.csv`, with these exact columns:

| Column | Type | Description |
|---|---|---|
| `month` | date (`YYYY-MM-01`) | First day of the reported month |
| `revenue_eur` | float | Total revenue for the month, consolidated in EUR |
| `shipments_processed` | int | Total number of shipments processed during the month (both countries) |
| `avg_revenue_per_shipment_eur` | float | Average revenue per shipment for the month |
| `market` | string | `"us"`, `"spain"`, or `"consolidated"` — use `"consolidated"` as the main row for the model |

The model's target variable is `revenue_eur` from the `consolidated` row.

---

### 3. KPIs and what a good model means here

- A high **Gini** matters to Thomas to confidently distinguish a normal low-season month (e.g. February) from an atypical drop that warrants investigation.
- **PSI** helps detect whether the volume mix between Los Angeles and Zaragoza shifted significantly between training and test — report it if it does, since it could signal an expansion or contraction of operations in one country.
- Report **MSE** in EUR², and also as a percentage of average monthly revenue, so Thomas and Ana can interpret it directly.

---

### 4. About the provided dataset

The file `data/raw/trackflow_sales.csv` contains **10 years** of monthly data (120 `consolidated` rows), from `2016-01` to `2025-12`. It already reflects the following patterns — you don't need to generate them, but you do need to understand them to interpret your model's results:

**Growth pattern:** base annual growth `X = 6%`, with variation `Y = 3%`. Each year, the actual growth `d` alternates between `X+Y` and `X-Y` (between 3% and 9%), always positive.

**Seasonality pattern (present every year in the dataset):**
- **November–December:** revenue rise of 25–35% relative to the average, from the Black Friday shipping peak and the holiday e-commerce season.
- **February:** revenue drop of 10–15% relative to the average, from the typical e-commerce slowdown after the peak season.
- All other months fluctuate moderately (±5%) around the annual growth trend.

The dataset was generated with a fixed random seed (`random_state=42`), so it's deterministic.

---

### 5. Business constraints

- All `revenue_eur` values must be positive.
- There must be no missing months in the 2016-01 to 2025-12 range.
- The provided dataset only includes the `consolidated` row; if you break revenue down by market as an additional feature, remember Los Angeles (US) carries a larger volume than Zaragoza (Spain) — use roughly 60/40 as a reference split.

---

### 6. Expected deliverables

- Training script in `scripts/` that loads `data/raw/trackflow_sales.csv`, splitting the first 8 years as training and the last 2 as test.
- Causal lag, rolling-statistic, and calendar/seasonal features engineered from the series (validated against the growth and seasonality pattern described above), with no leakage from future rows.
- A trained model (XGBoost or Random Forest) with all 4 metrics (MSE, PSI, Gini, K2 Score) calculated on the test set.
- A visualization showing the prediction and its variability range against the real data from the 2 test years.
- A unit test in `tests/pipelines/` validating the 8/2-year split.


CSV of trackflow_sales.csv: 

month,revenue_eur,shipments_processed,avg_revenue_per_shipment_eur,market
2016-01-01,760457.01,54867,13.86,consolidated
2016-02-01,664686.4,46352,14.34,consolidated
2016-03-01,767735.34,49788,15.42,consolidated
2016-04-01,779413.47,55633,14.01,consolidated
2016-05-01,744144.14,53651,13.87,consolidated
2016-06-01,728897.85,48561,15.01,consolidated
2016-07-01,714490.2,50034,14.28,consolidated
2016-08-01,761241.33,50380,15.11,consolidated
2016-09-01,729033.05,47931,15.21,consolidated
2016-10-01,773207.28,55948,13.82,consolidated
2016-11-01,997936.44,64466,15.48,consolidated
2016-12-01,963018.79,67962,14.17,consolidated
2017-01-01,854877.17,58513,14.61,consolidated
2017-02-01,731959.01,52171,14.03,consolidated
2017-03-01,845907.66,55469,15.25,consolidated
2017-04-01,842607.74,54187,15.55,consolidated
2017-05-01,820461.65,50834,16.14,consolidated
2017-06-01,807570.19,53411,15.12,consolidated
2017-07-01,844428.83,55264,15.28,consolidated
2017-08-01,847069.54,55765,15.19,consolidated
2017-09-01,834223.75,59973,13.91,consolidated
2017-10-01,795255.68,54883,14.49,consolidated
2017-11-01,1028397.99,71615,14.36,consolidated
2017-12-01,1030131.87,71191,14.47,consolidated
2018-01-01,853449.97,58137,14.68,consolidated
2018-02-01,742237.42,51905,14.3,consolidated
2018-03-01,822403.95,51240,16.05,consolidated
2018-04-01,854489.95,55995,15.26,consolidated
2018-05-01,814334.05,52369,15.55,consolidated
2018-06-01,813682.65,55315,14.71,consolidated
2018-07-01,883244.09,57578,15.34,consolidated
2018-08-01,846820.31,54846,15.44,consolidated
2018-09-01,870893.99,55613,15.66,consolidated
2018-10-01,819210.17,59021,13.88,consolidated
2018-11-01,1079093.19,74729,14.44,consolidated
2018-12-01,1070296.53,66644,16.06,consolidated
2019-01-01,952350.54,65409,14.56,consolidated
2019-02-01,795948.21,53963,14.75,consolidated
2019-03-01,955854.73,64151,14.9,consolidated
2019-04-01,896227.78,62281,14.39,consolidated
2019-05-01,923439.66,63994,14.43,consolidated
2019-06-01,925570.61,58030,15.95,consolidated
2019-07-01,908574.16,63404,14.33,consolidated
2019-08-01,963471.61,64146,15.02,consolidated
2019-09-01,880260.62,63283,13.91,consolidated
2019-10-01,881980.56,57608,15.31,consolidated
2019-11-01,1219956.68,82374,14.81,consolidated
2019-12-01,1153089.68,78335,14.72,consolidated
2020-01-01,992241.88,65842,15.07,consolidated
2020-02-01,804907.29,50719,15.87,consolidated
2020-03-01,899159.74,57898,15.53,consolidated
2020-04-01,962519.3,63785,15.09,consolidated
2020-05-01,923298.49,60189,15.34,consolidated
2020-06-01,908619.88,61228,14.84,consolidated
2020-07-01,940966.78,58481,16.09,consolidated
2020-08-01,980872.4,67975,14.43,consolidated
2020-09-01,945396.88,66437,14.23,consolidated
2020-10-01,984348.89,61948,15.89,consolidated
2020-11-01,1209890.06,78923,15.33,consolidated
2020-12-01,1239245.31,87456,14.17,consolidated
2021-01-01,1057471.9,70078,15.09,consolidated
2021-02-01,887264.28,58876,15.07,consolidated
2021-03-01,978960.02,67144,14.58,consolidated
2021-04-01,980908.02,61192,16.03,consolidated
2021-05-01,1069446.54,67686,15.8,consolidated
2021-06-01,1010588.03,72496,13.94,consolidated
2021-07-01,1069373.15,66545,16.07,consolidated
2021-08-01,987727.01,65980,14.97,consolidated
2021-09-01,986032.9,63086,15.63,consolidated
2021-10-01,1057814.37,74969,14.11,consolidated
2021-11-01,1337001.9,88426,15.12,consolidated
2021-12-01,1315339.77,82778,15.89,consolidated
2022-01-01,1053177.23,73597,14.31,consolidated
2022-02-01,926582.69,59587,15.55,consolidated
2022-03-01,1029616.99,70764,14.55,consolidated
2022-04-01,1113886.79,72519,15.36,consolidated
2022-05-01,1054765.21,70131,15.04,consolidated
2022-06-01,1021110.72,71207,14.34,consolidated
2022-07-01,1044150.32,68649,15.21,consolidated
2022-08-01,1032691.0,72065,14.33,consolidated
2022-09-01,1015802.87,66349,15.31,consolidated
2022-10-01,1032566.51,64657,15.97,consolidated
2022-11-01,1417904.68,101496,13.97,consolidated
2022-12-01,1351928.84,87731,15.41,consolidated
2023-01-01,1123796.35,79589,14.12,consolidated
2023-02-01,987056.79,65066,15.17,consolidated
2023-03-01,1153693.44,73577,15.68,consolidated
2023-04-01,1192427.95,83620,14.26,consolidated
2023-05-01,1110225.74,74864,14.83,consolidated
2023-06-01,1148014.16,76945,14.92,consolidated
2023-07-01,1183355.76,76742,15.42,consolidated
2023-08-01,1212865.9,86386,14.04,consolidated
2023-09-01,1145589.7,78411,14.61,consolidated
2023-10-01,1198695.27,83243,14.4,consolidated
2023-11-01,1468073.17,98661,14.88,consolidated
2023-12-01,1494874.34,103309,14.47,consolidated
2024-01-01,1161748.57,72519,16.02,consolidated
2024-02-01,1046003.73,65911,15.87,consolidated
2024-03-01,1197557.22,86031,13.92,consolidated
2024-04-01,1251053.19,79130,15.81,consolidated
2024-05-01,1247444.4,77868,16.02,consolidated
2024-06-01,1233109.87,86839,14.2,consolidated
2024-07-01,1189849.71,83148,14.31,consolidated
2024-08-01,1179769.0,84632,13.94,consolidated
2024-09-01,1177139.57,72843,16.16,consolidated
2024-10-01,1163583.17,74208,15.68,consolidated
2024-11-01,1543667.82,104161,14.82,consolidated
2024-12-01,1603521.02,99044,16.19,consolidated
2025-01-01,1306044.31,84152,15.52,consolidated
2025-02-01,1158868.49,79867,14.51,consolidated
2025-03-01,1359677.14,89511,15.19,consolidated
2025-04-01,1304281.43,83608,15.6,consolidated
2025-05-01,1241285.69,81664,15.2,consolidated
2025-06-01,1299171.32,81967,15.85,consolidated
2025-07-01,1254308.44,77859,16.11,consolidated
2025-08-01,1244265.94,87317,14.25,consolidated
2025-09-01,1311144.28,85029,15.42,consolidated
2025-10-01,1264409.36,89738,14.09,consolidated
2025-11-01,1739132.01,120857,14.39,consolidated
2025-12-01,1700717.6,111231,15.29,consolidated
}

ASSIGNMENT SPECS: 

{
    
Before you start: Read your CURRENT COMPANY BRIEFING before writing any code - it documents what each column means and the seasonality pattern of your company's historical sales, which is already included as a CSV in content/contexts/sales-forecasting/<company>/<company>_sales.csv in this repository.
Your challenge
You are building on your own fork of the company's monorepo selected at the beginning of the course - not on a new repository.
You've already prepared and split your company's historical data into training and test sets, and trained a first classification model. Now your tech lead needs something different: Leadership wants to know how much the company is going to sell in the coming months, not just classify an outcome into categories. That's a regression problem.
Your tech lead has opened a ticket based on an RFI that came in from Finance: they want to know whether, with the available historical data, it's feasible to predict future sales behavior with an acceptable margin of error before committing to building a full executive dashboard around it.
From: Your tech lead Subject: Ticket - Sales prediction model
Finance wants to know if we can predict sales for the coming months from the historical data. Before we promise them anything. I need a model trained and evaluated honestly: no claiming a low error just because the model memorized the past.
Non-negotiable criteria:
Use the first 8 years of data for training and the 2 most recent years to check the prediction - the model must not have seen those recent years during training.
I want a visualization showing the prediction along with its variability range (not a single optimistic number).
Justify why you chose XGBoost or Random Forest for this case - don't assume one is "better" without arguing it. Report the error with a metric I can explain to Finance without it sounding like a black box.
Complementary knowledge: Random Forest trains many decision trees on different subsets of the data and averages their results - it's simpler to explain and a good starting point. XGBoost trains trees sequentially, where each one corrects the errors of the previous one - it usually predicts better but is harder to explain and needs more tuning. Choose based on what your stakeholder actually needs: explainability or maximum accuracy.
How to Start the Project
1. If you still don't have a fork of your company's monorepo, create it on GitHub. We recommend opening and working on that fork in GitHub Codespaces; if you prefer to work locally, clone it to your machine.
2. From main in your fork, create a new branch for this project: git switch -c feature/sales-forecast-model (in Codespaces or in your local environment).
3. Verify that uv is installed with uv --version; if you don't have it, install it with curl -LsSf https://astral.sh/uv/install.sh | sh and, at the project root, initialize the environment with uv init (only if pyproject.toml does not already exist). Then add dependencies with uv add (for example scikit-learn. xgboost. pandas. matplotlib) - never use pip install or pipenv
4. Use your company's historical sales dataset already provided: in the monorepo it is located at data/raw/<company>_sales.csv, and in this reference repository at content/contexts/sales-forecasting/<company>/<company>_sales.csv ; do not generate or simulate it.
5. Read your full CURRENT COMPANY BRIEFING before writing code: it contains each column's meaning, the date range, and the seasonality pattern the dataset already reflects.
What You Need to Do
Data preparation
Load your company's historical sales dataset from the path that matches your working environment: data/raw/<company>_sales.csv in your monorepo or content/contexts/sales-forecasting/<company>/<company>_sales.csv in this reference repository, and verify the columns match those described in
your CONTEXT-company.md
Handle null or empty values before training
Split the dataset into training (the first 8 years) and checking/test (the 2 most recent years), so the model never sees the test years during training. Scale the variables that need it to avoid faulty comparisons between different magnitudes.
Model training
Train a regression model using XGBoost or Random Forest (pick one and document why) with scikit-learn
Document, in code or in a comment, the criteria used to choose the algorithm (data size, need for explainability, time available for tuning). Evaluation
Calculate and report at least the following metrics on the test set: MSE, PSI, Gini, and K2 Score
Explain in your implementation's README (or in a comment) what each metric measures and why a low MSE alone isn't enough.
Visualization
Generate a visualization showing the model's prediction along with the variability area of the result, compared against the real data from the 2 test years.
▲ IMPORTANT: Column names, dataset format, and specific values in your implementation must match what is specified in your CONTEXT.md. A generic implementation that ignores your company's context will not be accepted.
Testing
Add at least one unit test in tests/pipelines/ that validates the training/test split respects the 8-year/2-year rule and that there is no data leakage between the two sets.
What We Will Evaluate
The training/test split respects the 8-year/2-year rule and does not mix data between the two sets.
The trained model is XGBoost or Random Forest, with the choice explicitly justified.
All four metrics (MSE, PSI, Gini, K2 Score) are calculated and reported on the test set, not the training set.
There is a visualization showing the prediction along with its variability range, not just a point estimate.
The dataset used is the one provided in [data/raw/<company>_sales.csv.with no alterations that break the seasonality and growth pattern described in the company's CONTEXT.md.
The random seed (random_state/seed) is fixed so the experiment is reproducible.
The split's unit test passes correctly.
}

SUBMISSION INSTRUCTIONS: 
{
    How to Submit
1. Commit your changes with clear, descriptive messages.
2. Push your branch to your fork of the monorepo.
3. Open a Pull Request against the main branch of your own fork, briefly describing which algorithm you chose and why.
4. Include the metrics obtained on the test set in the PR description.
5. Wait for your tech lead's review before merging.
}