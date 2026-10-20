# KBC Ecosystems: Summary

`KBC_Ecosystems.xlsx` has one sheet ("Platte lijst") with two columns, *Ecosystem* and *Product or service*. It is KBC's catalogue of offerings and partners, the building blocks the ecosystem engine composes into journeys. `backend/scripts/import_ecosystems.py` turns it into `backend/app/ecosystem/catalogue.json`; see [../ECOSYSTEM.md](../ECOSYSTEM.md).

## Ecosystems and what's in them

| Ecosystem | Examples |
|-----------|----------|
| Housing | Home, bridging and renovation loans; home insurance; MyHome; Immoscoop (search, valuation); Setle (renovation costs and grants); Impact us today (window quotes); De Immowinkel (certificates); housing budget calculator; Home Loan/Insurance APIs and widgets |
| Mobility | Car and vehicle loans and insurance; MyMobility; VAB; parking (4411, Q-Park); Cambio car sharing; De Lijn, NMBS, MIVB tickets; Mobit, Blue-bike, Velo shared bikes; MoveSmart leasing; Q8 fuel; driving test prep; Car Insurance API/widget |
| Pensions | Pension savings fund and insurance; supplementary pensions for the self-employed; KBC Team Benefit Plan; Pension Fund Solutions |
| Investing | Investment plan; spare change investing; funds; thematic and responsible investing; managed investing; Bolero; portfolio management |
| Savings | Savings accounts; saving for someone else; Branch 21 insurance; term accounts |
| Business | Business accounts and cards; multi-currency; invoicing (Billit, Soluz.io, Go Solid); payment terminals, Paypage, Bancontact Pro; loans and credit lines; Start it @KBC, Innovation Banking, Boostpack; advisory (tax and legal, transfer, valuation, acquisition); working capital forecasts; Partner Hub products |
| Travel | Brussels Airport Fast Lane and Lounge Pass; Firsty travel eSIM; travel insurance |
| Energy and sustainability | Energy loan; solar panel and home battery calculators and quotes; insulation, heating and air-conditioning quotes (Impact us today); group energy purchase; consumption tips; ecoWise; Encon, Sweco, Kube ESG; business CO2 insights |
| Everyday banking and payments | Accounts, cards, Apple Pay, Wero, PayPal overview, split group expenses, Kate Wallet |
| Family and protection | Family, accident, life and funeral insurance; service vouchers |
| Health and wellbeing | Hospitalisation insurance; Helena medical records; KBC Hospital Care; Leadlife Plus |
| Wealth and estate planning | Private banker advice; Private Plan; inheritance planning; real estate service |
| Work and employees | NOWJOBS flexible workers; Human Capital Solutions; Employee Care; Team Protect Plan; share option plans |
| International business | Documentary collections and credits; guarantees; Flexims; forfaiting; FX and interest hedging; Go&Deal Pro |
| Business protection | Liability, legal, property and income insurance for businesses |
| Agriculture and horticulture | Agroflex Credit; agriculture and greenhouse insurance |
| Administration and documents | IPEX registered email; digital vault; eBox; Cera share administration |
| Shopping and everyday services | Joyn loyalty points and cards; mobile top-ups; Kom op tegen Kanker donations; financial news; Kate Coins |
| Digital platforms and assistance | KBC Mobile, Touch, Business Dashboard, Business app, Reach; **Kate** (assistant: search documents, query income and expenses, manage cards, make transfers, report claims); Partner Hub; **Developer Portal** |
| Security | Online fraud insurance |
| General integrations | Instalment Loan Partner Hub; PSD2 AIS and PIS; application status webhooks |

## Takeaways

- **Integration points:** the machine-accessible surfaces are the Developer Portal, PSD2 AIS/PIS, application status webhooks, the Home Loan/Home Insurance/Car Insurance APIs and widgets, and Partner Hub. Kate is the conversational entry point.
- **Cross-ecosystem journeys** are where "before they realise they need help" fits best. Examples: a home purchase touches Housing, Energy, Mobility, Insurance and Administration; starting a business touches Business, Pensions and Business protection.
- **Existing KBC partners**: Immoscoop, Setle, Impact us today, Cambio, VAB, MoveSmart, Firsty, Billit, Encon, Sweco, Kube ESG, NOWJOBS.
