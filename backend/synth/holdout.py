"""Blind holdout set for intent detection.

~300 hand-designed customers as of 2026-10-20, written without looking at the detector rules. Each goal has its own
positive variations (different amounts, timings, merchant spellings in Dutch and French, noise) and ~40% of the set
is hard negatives: realistic lookalikes labelled `near_miss:<goal>`. A few plain customers carry no label at all.

    from synth.holdout import holdout_customers
    for customer, txs, balance_today in holdout_customers():
        ...

Ground truth: customer.ground_truth = {"events": [{"type": "goal:<id>" | "near_miss:<id>", "date": "YYYY-MM-DD"}],
"holdout": True}. Customer ids start at 900001 so they never clash with the regular portfolio.
"""
from __future__ import annotations

import datetime as dt
import random
from typing import Callable

from app.schemas import Customer, Transaction
from synth.generate import TxBuilder, add_months, calibrate_balance, fixed_band, living_costs, safe_date

AS_OF = dt.date(2026, 10, 20)
HISTORY_START = dt.date(2025, 6, 1)
FIRST_ID = 900001

GOALS = (
    # existing
    "buy_home", "energy_upgrade", "new_baby", "go_freelance", "get_paid", "retire_well", "travel", "peace_of_mind",
    "job_change", "mobility", "first_employee", "inheritance", "study_start",
    # life-event and business goals
    "side_job", "go_international", "care_parent", "move_house", "sell_business", "back_on_track", "farm_growth",
    "ev_switch", "first_investment", "together", "separation",
)

# ----------------------------------------------------------------------------------
# Own vocabulary (deliberately different from synth/generate.py where possible)
# ----------------------------------------------------------------------------------

NL_FIRST = ["Jonas", "Ellen", "Kobe", "Sien", "Robbe", "Lies", "Jens", "Hanne", "Thibault", "Febe", "Arne", "Ines",
            "Mathias", "Eline", "Wannes", "Jolien", "Brecht", "Lien", "Siebe", "Charlotte", "Joris", "Griet", "Lander",
            "Margot", "Toon", "Annelies", "Gilles", "Sofie", "Maarten", "Evy"]
FR_FIRST = ["Quentin", "Aurélie", "Romain", "Gaëlle", "Cédric", "Noémie", "Arnaud", "Justine", "Benoît", "Pauline",
            "Grégory", "Mélanie", "Thomas", "Valérie", "Loïc", "Sarah", "Damien", "Ophélie"]
NL_LAST = ["Verbeke", "De Clercq", "Desmet", "Van Damme", "Coppens", "Hermans", "Cools", "Van Acker", "Segers",
           "Verstraeten", "De Vos", "Michiels", "Martens", "Smets", "Van Hecke", "Declercq", "Bogaert", "Verlinden"]
FR_LAST = ["Collignon", "Delvaux", "Masson", "Hubert", "Gilson", "Lejeune", "Wauters", "Thiry", "Close", "Piron",
           "Henrard", "Dethier", "François", "Goffin"]
NL_CITY = ["Oudenaarde", "Turnhout", "Lier", "Sint-Niklaas", "Ieper", "Tienen", "Geel", "Dendermonde", "Brugge",
           "Herentals", "Leuven", "Gent", "Antwerpen", "Hasselt", "Diest", "Waregem"]
FR_CITY = ["Verviers", "Huy", "Nivelles", "Ottignies", "Dinant", "Mouscron", "Marche-en-Famenne", "Liège", "Namur"]

EMPLOYERS = ["Agfa-Gevaert NV", "Etex Group", "Vandemoortele NV", "Puratos", "Ontex BV", "Stad Antwerpen",
             "UCB Pharma", "Lotus Bakeries", "Securitas NV", "Infrabel", "AZ Delta", "Groep Van Roey", "Ores SC",
             "CHU de Liège", "Ville de Namur", "Sonaca SA", "IBA SA", "Aquafin NV", "Van de Velde NV", "Vandewiele",
             "Lineas", "Duvel Moortgat", "Picanol", "Televic", "Arcadis Belgium"]
LANDLORDS = ["Immo Vandenberghe", "Dhr. De Wilde", "Mevr. Pollet", "Woonhaven Antwerpen", "Immo Callebaut",
             "Propriétaire M. Collard", "Immo Lemaire SRL", "Dhr. en Mevr. Ceulemans", "Gestion Locative Mosane",
             "Immo Ardennes SRL", "Mevr. Van Laere", "Dhr. Wuyts"]
MORTGAGES = ["KBC Woonkrediet", "Hypothecaire lening KBC", "Crédit hypothécaire CBC", "KBC woonlening"]
NOISE_SHOPS = ["Hubo", "Zeeman", "Torfs", "JBC", "Gamma", "Mediamarkt", "Coolblue", "Vanden Borre", "Blokker",
               "Cora", "Intermarché", "Brico Plan-it", "Trafic", "AS Adventure", "Dille & Kamille", "Krëfel"]
NOISE_FOOD = ["Exki", "Panos", "Le Pain Quotidien", "Quick", "Ellis Gourmet Burger", "Frituur De Kroon",
              "Bavet", "Balls & Glory", "Délifrance", "Starbucks Gent-Sint-Pieters"]
NOISE_HEALTH = ["Apotheek De Lelie", "Pharmacie Multipharma", "Tandarts Verhaegen", "Kiné Bastin", "Huisartsenpraktijk Arcade"]
FREELANCE_CLIENTS = ["Kraftwerk Design BV", "Vzw Ondersteboven", "Brouwerij Het Anker", "Gemeente Zemst",
                     "Atelier Noord CommV", "Agence Pixelle SRL", "Bureau Verhaeghe", "Media Huis Leie",
                     "Solar Concept BV", "Cabinet Delmotte", "Studio Kwadraat", "De Werf vzw", "Clinique Saint-Luc",
                     "Bouwbedrijf Moens", "Hotel Pand 13", "Zorgnet Kempen"]


class P:
    """One customer under construction."""

    def __init__(self, cid: int, rng: random.Random, age: int, lang: str | None = None,
                 start: dt.date = HISTORY_START):
        self.cid = cid
        self.rng = rng
        self.lang = lang or rng.choice(["nl", "nl", "nl", "fr"])
        self.age = age
        nl = self.lang == "nl"
        self.first = rng.choice(NL_FIRST if nl else FR_FIRST)
        self.last = rng.choice(NL_LAST if nl else FR_LAST)
        self.city = rng.choice(NL_CITY if nl else FR_CITY)
        self.b = TxBuilder(cid, rng, start, AS_OF)
        self.start = start
        self.products = ["current", "savings"]
        self.events: list[dict] = []
        self.band = (300.0, rng.uniform(7000, 14000), rng.uniform(2500, 5000))
        self.start_balance = rng.uniform(1500, 6000)
        self.sweep = ("savings_transfer", rng.choice(["KBC Spaarrekening", "Spaarrekening KBC", "Compte épargne KBC"]))

    # --- labels ---
    def goal(self, gid: str, d: dt.date) -> None:
        self.events.append({"type": f"goal:{gid}", "date": d.isoformat()})

    def near(self, gid: str, d: dt.date) -> None:
        self.events.append({"type": f"near_miss:{gid}", "date": d.isoformat()})

    # --- helpers ---
    def ago(self, days: int, jitter: int = 0) -> dt.date:
        if jitter:
            days += self.rng.randint(-jitter, jitter)
        return AS_OF - dt.timedelta(days=max(0, days))

    def add(self, d: dt.date, amount: float, category: str, cp: str) -> None:
        self.b.add(min(d, AS_OF), amount, category, cp)

    def add_signed(self, d: dt.date, amount: float, category: str, cp: str) -> None:
        self.b.add_signed(min(d, AS_OF), amount, category, cp)

    def monthly(self, start: dt.date, end: dt.date, day: int, amount, category: str, cp: str,
                jitter: float = 0.0, jdays: int = 0) -> None:
        self.b.monthly(max(start, self.start), min(end, AS_OF), day, amount, category, cp, jitter, jdays)

    # --- base lives ---
    def life(self, scale: float = 1.0, start: dt.date | None = None, end: dt.date | None = None) -> None:
        s, e = start or self.start, end or AS_OF
        living_costs(self.b, s, e, scale)
        self.b.scatter(s, e, "other", NOISE_SHOPS, 1.5 * scale, 12, 140)
        self.b.scatter(s, e, "leisure", NOISE_FOOD, 2.0 * scale, 6, 45)
        self.b.scatter(s, e, "healthcare", NOISE_HEALTH, 0.6, 9, 70)

    def employee(self, salary: float | None = None, employer: str | None = None, day: int | None = None,
                 start: dt.date | None = None, end: dt.date | None = None, bonus: bool | None = None) -> str:
        rng = self.rng
        employer = employer or rng.choice(EMPLOYERS)
        salary = salary or rng.uniform(2300, 3900)
        day = day or rng.choice([25, 26, 27, 28, 30, 1])
        label = employer if rng.random() < 0.6 else ("Loon " if self.lang == "nl" else "Salaire ") + employer
        self.monthly(start or self.start, end or AS_OF, day, salary, "salary", label, jitter=0.01, jdays=1)
        if bonus is None:
            bonus = rng.random() < 0.45
        if bonus:
            dec = dt.date(2025, 12, rng.randint(15, 22))
            if (start or self.start) <= dec <= (end or AS_OF):
                self.add(dec, salary * rng.uniform(0.85, 1.0), "salary",
                         f"{employer} (eindejaarspremie)" if self.lang == "nl" else f"{employer} (prime de fin d'année)")
        return label

    def rent(self, amount: float | None = None, landlord: str | None = None, start: dt.date | None = None,
             end: dt.date | None = None, day: int | None = None) -> str:
        landlord = landlord or self.rng.choice(LANDLORDS)
        amount = amount or self.rng.uniform(650, 1150)
        self.monthly(start or self.start, end or AS_OF, day or self.rng.randint(1, 5), amount, "rent", landlord)
        return landlord

    def mortgage(self, amount: float | None = None, start: dt.date | None = None) -> None:
        self.products.append("mortgage")
        self.products.append("home_insurance")
        self.monthly(start or self.start, AS_OF, self.rng.randint(1, 6), amount or self.rng.uniform(700, 1400),
                     "mortgage", self.rng.choice(MORTGAGES))
        self.b.yearly(start or self.start, AS_OF, self.rng.randint(1, 12), 12, self.rng.uniform(280, 520),
                      "insurance_home", self.rng.choice(["KBC Verzekeringen", "AG Insurance", "Ethias"]))

    def car(self) -> None:
        self.products.append("car_insurance")
        self.b.yearly(self.start, AS_OF, self.rng.randint(1, 12), 3, self.rng.uniform(450, 900), "insurance_car",
                      self.rng.choice(["KBC Verzekeringen", "Baloise", "P&V"]))

    def freelancer(self, clients: list[str] | None = None, start: dt.date | None = None,
                   end: dt.date | None = None, lo: float = 900, hi: float = 3200, per_month: float = 2.0,
                   fund: str | None = None) -> list[str]:
        rng = self.rng
        clients = clients or rng.sample(FREELANCE_CLIENTS, rng.randint(3, 5))
        s, e = start or self.start, end or AS_OF
        y, m = s.year, s.month
        cur = safe_date(y, m, 1)
        while cur <= e:
            n = max(1, int(round(rng.gauss(per_month, 0.7))))
            for _ in range(n):
                d = safe_date(cur.year, cur.month, rng.randint(3, 27))
                if s <= d <= e:
                    self.add(d, rng.uniform(lo, hi), "invoice_income", rng.choice(clients))
            cur = add_months(cur, 1)
        fund = fund or rng.choice(["Xerius", "Liantis", "Acerta", "Securex", "UCM"])
        for q in _quarter_days(s, AS_OF, (3, 6, 9, 12), rng):
            self.add(q, rng.uniform(800, 1500), "social_contribution", fund)
        for q in _quarter_days(s, AS_OF, (1, 4, 7, 10), rng):
            self.add(q, rng.uniform(900, 2200), "vat_payment", "FOD Financiën - btw")
        return clients

    def retiree(self, pension: float | None = None, payer: str | None = None) -> None:
        payer = payer or self.rng.choice(["Federale Pensioendienst", "Service fédéral des Pensions", "FPD Pensioen"])
        self.monthly(self.start, AS_OF, self.rng.choice([1, 3, 5]), pension or self.rng.uniform(1500, 2600),
                     "pension", payer)

    def kids(self, n: int = 1, payer: str | None = None) -> None:
        payer = payer or self.rng.choice(["Groeipakket Infino", "FONS Groeipakket", "Kidslife Vlaanderen",
                                          "Famiwal allocations familiales", "Parentia"])
        self.monthly(self.start, AS_OF, self.rng.randint(5, 10), 175 * n, "child_benefit", payer)
        self.b.scatter(self.start, AS_OF, "school", ["Schoolrekening Sint-Lodewijk", "Ecole communale Les Tilleuls",
                                                       "Studio 100 Kampen"], 0.4, 20, 160)

    def build(self) -> tuple[Customer, list[Transaction], float]:
        lo, hi, target = self.band
        bal = calibrate_balance(self.b, self.start_balance, fixed_band(lo, hi, target), excess=self.sweep)
        txs = sorted(self.b.txs, key=lambda t: (t.date, t.amount))
        txs = [t.model_copy(update={"id": self.cid * 100000 + i}) for i, t in enumerate(txs, 1)]
        customer = Customer(id=self.cid, first_name=self.first, last_name=self.last,
                            birth_year=AS_OF.year - self.age, city=self.city, language=self.lang,
                            products=sorted(set(self.products)),
                            ground_truth={"events": self.events, "holdout": True})
        return customer, txs, bal


def _quarter_days(start: dt.date, end: dt.date, months: tuple[int, ...], rng: random.Random) -> list[dt.date]:
    out = []
    for y in range(start.year, end.year + 1):
        for m in months:
            d = safe_date(y, m, rng.randint(15, 24))
            if start <= d <= end:
                out.append(d)
    return out


def _salaried(p: P, housing: str = "rent", scale: float | None = None) -> str:
    emp = p.employee()
    if housing == "rent":
        p.rent()
    elif housing == "mortgage":
        p.mortgage()
    p.life(scale or p.rng.uniform(0.8, 1.2))
    if p.rng.random() < 0.6:
        p.car()
    return emp


def _pick(p: P, *options):
    return p.rng.choice(options)


# ----------------------------------------------------------------------------------
# Scenarios. Each takes (p, v) where v is the variant index; returns nothing, labels via p.goal / p.near.
# ----------------------------------------------------------------------------------

# ---------- buy_home ----------
def pos_buy_home(p: P, v: int) -> None:
    p.age = p.rng.randint(26, 39)
    _salaried(p, "rent")
    rng = p.rng
    start = p.ago(rng.randint(60, 150))
    # monthly savings effort
    p.monthly(p.ago(330), AS_OF, rng.randint(2, 6), rng.uniform(300, 900), "savings_transfer",
              _pick(p, "Spaarrekening woning", "KBC Spaarrekening", "Epargne maison"))
    portal = ["Immoweb", "Zimmo", "Immovlan", "Immoweb Premium"][v % 4]
    p.monthly(start, AS_OF, rng.randint(9, 20), rng.choice([9.99, 14.95, 19.0]), "subscription",
              f"{portal} zoekabonnement" if p.lang == "nl" else f"{portal} abonnement recherche")
    if v % 3 != 2:
        p.add(p.ago(rng.randint(10, 45)), rng.uniform(380, 650), "property",
              _pick(p, "Bouwkundige keuring Vanhove", "Expertise immobilière Ledoux", "Woningkeuring Plus"))
    if v % 3 == 1:
        p.add(p.ago(rng.randint(3, 20)), rng.uniform(18000, 32000), "notary",
              _pick(p, "Notaris Vercruysse (voorschot)", "Notaire Delhaye (acompte)", "Notariskantoor Bral derdenrekening"))
        p.start_balance += 30000
    p.goal("buy_home", start)


def nm_buy_home(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # landlord who advertises his flat on Immoweb, already owns
        _salaried(p, "mortgage")
        p.monthly(p.start, AS_OF, 3, rng.uniform(650, 800), "other", "Huurder Dhr. Van Lierde (huur studio)")
        p.add(p.ago(40), 59.0, "subscription", "Immoweb advertentie")
    elif v == 1:  # renter whose rent is indexed, saves for a car
        _salaried(p, "rent")
        p.monthly(p.ago(300), AS_OF, 4, rng.uniform(150, 300), "savings_transfer", "KBC Spaarrekening")
    elif v == 2:  # notary for a will, 64
        p.age = 64
        _salaried(p, "mortgage")
        p.add(p.ago(30), rng.uniform(250, 600), "notary", "Notaris Lammens (testament)")
    elif v == 3:  # inspection of the rented flat at end of lease (plaatsbeschrijving)
        _salaried(p, "rent")
        p.add(p.ago(25), rng.uniform(120, 260), "property", "Plaatsbeschrijving Expertisebureau Mortier")
    else:  # owner paying a surveyor for a garden shed permit
        _salaried(p, "mortgage")
        p.add(p.ago(50), rng.uniform(300, 700), "property", "Landmeter De Coninck (opmeting)")
    p.near("buy_home", p.ago(30))


# ---------- energy_upgrade ----------
def pos_energy_upgrade(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(30, 60)
    if v % 2 == 0:  # bought a house 6-16 months ago
        bought = p.ago(rng.randint(180, 480))
        p.rent(end=bought - dt.timedelta(days=20))
        p.mortgage(start=bought)
        p.add(bought - dt.timedelta(days=5), rng.uniform(25000, 45000), "notary",
              _pick(p, "Notaris Goethals (aankoop woning)", "Notaire Remacle (achat)", "Notariskantoor Van Eeckhout"))
        p.start_balance += 50000
        p.employee()
        p.life()
        p.goal("energy_upgrade", bought)
    else:  # owner whose energy bill jumped and stayed high
        p.employee()
        p.mortgage()
        p.life()
        jump = p.ago(rng.randint(60, 140))
        old, new = rng.uniform(110, 170), rng.uniform(240, 360)
        prov = _pick(p, "Engie Electrabel", "Luminus", "Mega", "Bolt Energie", "TotalEnergies Power")
        p.monthly(p.start, AS_OF, 17, lambda d: new if d >= jump else old, "utilities", f"{prov} voorschot",
                  jitter=0.04)
        if v % 4 == 1:
            p.add(p.ago(10), rng.uniform(250, 420), "other", "Energieadvies Vlaanderen (EPC-attest)")
        p.goal("energy_upgrade", jump)


def nm_energy_upgrade(p: P, v: int) -> None:
    rng = p.rng
    if v in (0, 1):  # renter with a jumping bill: can't renovate someone else's house
        p.employee()
        p.rent()
        p.life()
        jump = p.ago(90)
        p.monthly(p.start, AS_OF, 17, lambda d: 290.0 if d >= jump else 140.0, "utilities", "Engie voorschot")
    elif v == 2:  # owner, single annual settlement spike
        p.employee()
        p.mortgage()
        p.life()
        p.add(p.ago(35), rng.uniform(550, 900), "utilities", "Luminus jaarafrekening")
    elif v == 3:  # owner for 10 years with a stable bill and a new roof gutter repair
        p.employee()
        p.mortgage()
        p.life()
        p.add(p.ago(60), 780.0, "other", "Dakwerken Boone (dakgoot herstelling)")
    else:  # bought a garage box (notary) but rents the home
        p.employee()
        p.rent()
        p.life()
        p.add(p.ago(200), 2400.0, "notary", "Notaris Pieters (aankoop garagebox)")
    p.near("energy_upgrade", p.ago(40))


# ---------- new_baby ----------
BABY_SHOPS = ["Prénatal", "Baby2Mom", "Kiabi Bébé", "Babyshop Lier", "Aubert", "Orchestra Kids"]


def pos_new_baby(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(26, 38)
    _salaried(p, _pick(p, "rent", "mortgage"))
    if v % 2 == 0:  # pregnancy: prenatal costs, gynaecologist, baby shopping ramp
        start = p.ago(rng.randint(70, 130))
        p.b.scatter(start, AS_OF, "baby", BABY_SHOPS, 2.5, 25, 260)
        p.b.scatter(start, AS_OF, "healthcare", ["Gynaecoloog Dr. Moerman", "Echografie AZ Sint-Jan",
                                                 "Gynécologue Dr. Lambot"], 1.0, 40, 90)
        p.add(p.ago(rng.randint(5, 30)), rng.uniform(400, 900), "furniture", _pick(p, "Bopita kinderkamer", "Childhome", "Ikea"))
        p.goal("new_baby", start)
    else:  # born 1-4 months ago
        born = p.ago(rng.randint(25, 120))
        p.add(born + dt.timedelta(days=20), 1214.0, "child_benefit",
              _pick(p, "Groeipakket startbedrag", "Kidslife startbedrag", "Famiwal allocation de naissance"))
        p.monthly(born + dt.timedelta(days=30), AS_OF, 8, 179.0, "child_benefit",
                  _pick(p, "Groeipakket Infino", "FONS Groeipakket", "Famiwal"))
        p.b.scatter(born - dt.timedelta(days=60), AS_OF, "baby", BABY_SHOPS, 3.0, 15, 180)
        p.add(born, rng.uniform(300, 900), "healthcare",
              _pick(p, "AZ Sint-Jan (bevalling)", "CHR Citadelle (maternité)", "UZ Gent kraamafdeling"))
        if v % 4 == 1:
            p.monthly(born + dt.timedelta(days=75), AS_OF, 2, rng.uniform(380, 620), "childcare",
                      _pick(p, "Kinderdagverblijf Pimpampoentje", "Crèche Les Lutins"))
        p.goal("new_baby", born)


def nm_new_baby(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # grandparent buying a gift
        p.age = 66
        p.retiree()
        p.life(0.8)
        p.add(p.ago(20), 145.0, "baby", "Prénatal (cadeaubon)")
    elif v == 1:  # family with kids aged 6 and 9
        p.age = 41
        _salaried(p, "mortgage")
        p.kids(2)
    elif v == 2:  # aunt buying a kraamcadeau + baby shower restaurant
        p.age = 33
        _salaried(p, "rent")
        p.add(p.ago(15), 65.0, "baby", "Baby2Mom (geschenk)")
        p.add(p.ago(14), 85.0, "leisure", "Brasserie De Markt (babyborrel)")
    elif v == 3:  # childminder paid by parents (income): looks like childcare
        p.age = 45
        p.monthly(p.start, AS_OF, 2, 1650.0, "other", "Ouders Lemmens (onthaalouder)")
        p.monthly(p.start, AS_OF, 3, 1500.0, "other", "Ouders Bastiaens (onthaalouder)")
        p.rent()
        p.life()
    else:  # pet "baby": vet and pet shop ramp
        p.age = 29
        _salaried(p, "rent")
        p.b.scatter(p.ago(90), AS_OF, "other", ["Dierenarts De Poot", "Tom&Co", "Maxi Zoo"], 3.0, 15, 120)
    p.near("new_baby", p.ago(20))


# ---------- go_freelance ----------
def pos_go_freelance(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(27, 52)
    stop = p.ago(rng.randint(45, 150))
    p.employee(end=stop)
    p.rent() if v % 2 else p.mortgage()
    p.life()
    first = stop + dt.timedelta(days=rng.randint(15, 40))
    clients = rng.sample(FREELANCE_CLIENTS, rng.randint(1, 3))
    p.freelancer(clients, start=first, lo=1200, hi=4200, per_month=1.3,
                 fund=_pick(p, "Xerius (zelfstandige)", "Liantis sociaal verzekeringsfonds", "UCM caisse sociale"))
    if v % 3 == 0:
        p.add(stop + dt.timedelta(days=rng.randint(3, 12)), rng.uniform(85, 110), "other",
              _pick(p, "Ondernemingsloket Formalis (inschrijving KBO)", "Guichet d'entreprises UCM (inscription BCE)"))
    if v % 3 == 1:
        p.add(stop + dt.timedelta(days=10), rng.uniform(900, 1900), "other", _pick(p, "Coolblue (laptop)", "Apple Store", "Bureau Plus"))
    p.start_balance += 6000
    p.goal("go_freelance", first)


def nm_go_freelance(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # teacher with a one-off summer-camp invoice
        p.age = 37
        _salaried(p, "rent")
        p.add(dt.date(2026, 8, 12), 640.0, "invoice_income", "Vzw Speelplein Krokus (monitor)")
    elif v == 1:  # retirement: salary stops, pension starts
        p.age = 65
        stop = p.ago(110)
        p.employee(end=stop)
        p.monthly(stop + dt.timedelta(days=30), AS_OF, 3, 2100.0, "pension", "Federale Pensioendienst")
        p.mortgage()
        p.life()
        p.near("job_change", stop)
    elif v == 2:  # employee giving a paid lecture
        p.age = 46
        _salaried(p, "mortgage")
        p.add(p.ago(35), 450.0, "invoice_income", "Hogeschool PXL (gastcollege)")
    elif v == 3:  # career break: salary replaced by Vlaamse aanmoedigingspremie, no invoices
        p.age = 39
        stop = p.ago(100)
        p.employee(end=stop)
        p.monthly(stop + dt.timedelta(days=20), AS_OF, 10, 1050.0, "benefit", "RVA loopbaanonderbreking")
        p.rent()
        p.life(0.8)
    else:  # employee whose employer reimburses expenses (looks like a 2nd payer)
        p.age = 34
        emp = _salaried(p, "rent")
        p.monthly(p.ago(150), AS_OF, 15, rng.uniform(80, 220), "other", "Onkostennota " + emp.replace("Loon ", ""))
    p.near("go_freelance", p.ago(60))


# ---------- get_paid ----------
def pos_get_paid(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(30, 58)
    regular = rng.choice(FREELANCE_CLIENTS)
    others = [c for c in rng.sample(FREELANCE_CLIENTS, 4) if c != regular][:3]
    p.freelancer(others, lo=600, hi=2200, per_month=1.4)
    last_paid = p.ago(rng.randint(70, 115))
    p.monthly(p.start, last_paid, rng.randint(5, 12), rng.uniform(2200, 4500), "invoice_income", regular, jitter=0.03)
    p.rent() if v % 2 else p.mortgage()
    p.life()
    p.goal("get_paid", last_paid + dt.timedelta(days=35))


def nm_get_paid(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(30, 55)
    if v == 0:  # client renamed after a merger: payments continue under a new name
        cut = p.ago(90)
        p.freelancer(rng.sample(FREELANCE_CLIENTS, 2), lo=600, hi=1800, per_month=1.0)
        p.monthly(p.start, cut, 8, 3100.0, "invoice_income", "Studio Kwadraat BV", jitter=0.02)
        p.monthly(cut + dt.timedelta(days=1), AS_OF, 8, 3100.0, "invoice_income", "Kwadraat Group NV", jitter=0.02)
    elif v == 1:  # quarterly client: nothing for 70 days is normal
        p.freelancer(rng.sample(FREELANCE_CLIENTS, 3), lo=700, hi=2000, per_month=1.5)
        for d in (dt.date(2025, 7, 10), dt.date(2025, 10, 9), dt.date(2026, 1, 12), dt.date(2026, 4, 10),
                  dt.date(2026, 7, 9), dt.date(2026, 10, 12)):
            p.add(d, 6400.0, "invoice_income", "Zorgnet Kempen (kwartaalfactuur)")
    elif v == 2:  # summer work pause across all clients, resumed in September
        clients = rng.sample(FREELANCE_CLIENTS, 3)
        p.freelancer(clients, end=dt.date(2026, 6, 30), per_month=2.0)
        p.freelancer(clients, start=dt.date(2026, 9, 1), per_month=2.0)
    elif v == 3:  # finished project, client paid the final invoice
        p.freelancer(rng.sample(FREELANCE_CLIENTS, 3), lo=700, hi=2400, per_month=1.6)
        p.monthly(p.start, p.ago(100), 6, 2500.0, "invoice_income", "Solar Concept BV")
        p.add(p.ago(75), 4200.0, "invoice_income", "Solar Concept BV (eindfactuur)")
    else:  # salaried person whose tenant pays rent (landlord) and is late once
        _salaried(p, "mortgage")
        p.monthly(p.start, AS_OF, 4, 720.0, "other", "Huur appartement Dhr. Bauwens", jdays=3)
    if v != 4:
        p.rent()
        p.life()
    p.near("get_paid", p.ago(40))


# ---------- retire_well ----------
def pos_retire_well(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(51, 63)
    p.employee(salary=rng.uniform(3300, 5200))
    p.mortgage() if v % 3 == 0 else None
    p.life(1.1)
    if v % 2:
        p.products = ["current"]
    lo = rng.uniform(55000, 140000)
    p.band = (lo, lo * 1.4, lo * 1.2)
    p.start_balance = lo * 1.1
    p.goal("retire_well", p.ago(60))


def nm_retire_well(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # 44 with a big balance: too early
        p.age = 44
        p.employee(salary=4200)
        p.life()
        p.band = (70000, 95000, 85000)
        p.start_balance = 80000
    elif v == 1:  # 58, sold the house: money is earmarked for the next one (notary)
        p.age = 58
        p.employee(salary=3600)
        p.life()
        p.add_signed(p.ago(50), 285000.0, "property", "Notaris Claeys (verkoop woning)")
        p.add(p.ago(12), 270000.0, "notary", "Notaris Claeys (aankoop appartement)")
        p.start_balance = 9000
    elif v == 2:  # 60, already invests monthly
        p.age = 60
        p.employee(salary=3900)
        p.products += ["investment_plan"]
        p.monthly(p.start, AS_OF, 5, 500.0, "savings_transfer", "KBC Beleggingsplan")
        p.life()
    elif v == 3:  # 57 living tight, modest balance
        p.age = 57
        p.employee(salary=2100)
        p.rent()
        p.life(0.8)
        p.band = (200, 2500, 1200)
    else:  # 66: already retired with a modest balance
        p.age = 66
        p.retiree()
        p.life(0.8)
    p.near("retire_well", p.ago(60))


# ---------- travel ----------
TRAVEL = ["Brussels Airlines", "TUI fly", "Ryanair", "Sunweb", "Booking.com", "Airbnb", "Corendon", "Jetair",
          "Transavia", "Vliegtickets.be", "Connections reisbureau", "Pierre & Vacances"]


def pos_travel(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(24, 70)
    _salaried(p, _pick(p, "rent", "mortgage")) if p.age < 66 else (p.retiree(), p.life())
    d = p.ago(rng.randint(3, 60))
    p.add(d, rng.uniform(450, 3200), "leisure" if v % 2 else "other", TRAVEL[v % len(TRAVEL)])
    if v % 3 == 0:
        p.add(d + dt.timedelta(days=rng.randint(1, 10)), rng.uniform(150, 700), "leisure",
              _pick(p, "Airbnb", "Booking.com", "Hotels.com"))
    p.goal("travel", d)


def nm_travel(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # refund of a cancelled trip
        p.add_signed(p.ago(20), 1240.0, "other", "TUI terugbetaling annulatie")
    elif v == 1:  # train commuter
        p.monthly(p.start, AS_OF, 2, 78.0, "transport", "NMBS treinabonnement")
    elif v == 2:  # one hotel night in Belgium for a wedding
        p.add(p.ago(30), 95.0, "leisure", "Booking.com Hotel Ibis Brugge")
    elif v == 3:  # Airbnb host payout (income, not a trip)
        p.add_signed(p.ago(25), 410.0, "other", "Airbnb payout")
        p.add_signed(p.ago(55), 380.0, "other", "Airbnb payout")
    else:  # last year's holiday, nothing since
        p.add(dt.date(2025, 7, 2), 1650.0, "leisure", "Sunweb")
    p.near("travel", p.ago(20))


# ---------- peace_of_mind ----------
def pos_peace_of_mind(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(67, 86)
    p.retiree()
    p.life(0.7)
    if v % 2 == 0:  # suspicious new payee: repeated large transfers to unknown accounts
        payee = _pick(p, "Global Invest Ltd", "Crypto Secure Wallet", "J. Morrison", "Western Union",
                      "Safe Account BE (helpdesk bank)", "Bitvavo")
        for k in range(rng.randint(2, 4)):
            p.add(p.ago(rng.randint(2, 25) + k * 6), rng.uniform(1500, 6000), "other", payee)
        p.start_balance += 25000
        p.goal("peace_of_mind", p.ago(25))
    else:  # large balance not working, no savings product
        p.products = ["current"]
        lo = rng.uniform(60000, 160000)
        p.band = (lo, lo * 1.4, lo * 1.15)
        p.start_balance = lo * 1.1
        p.goal("peace_of_mind", p.ago(60))


def nm_peace_of_mind(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(67, 82)
    p.retiree()
    p.life(0.7)
    if v == 0:  # one large payment to a known contractor
        p.add(p.ago(15), 4800.0, "other", "Dakwerken Vermeire (factuur 2026-118)")
    elif v == 1:  # regular gifts to grandchildren for years
        p.monthly(p.start, AS_OF, 20, 50.0, "other", "Kleinzoon Arno (zakgeld)")
    elif v == 2:  # comfortable but money sits on savings
        p.band = (3000, 9000, 5000)
        p.monthly(p.start, AS_OF, 4, 400.0, "savings_transfer", "KBC Spaarrekening")
    elif v == 3:  # pays a home help service (known, regular)
        p.monthly(p.start, AS_OF, 10, 140.0, "other", "Dienstencheques Sodexo")
    else:  # new payee: grandchild's student rent once
        p.add(p.ago(12), 450.0, "other", "Kot Leuven (huur kleindochter)")
    p.near("peace_of_mind", p.ago(20))


# ---------- job_change ----------
def pos_job_change(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(25, 55)
    old = rng.choice(EMPLOYERS)
    if v % 2 == 0:  # switched employer
        switch = p.ago(rng.randint(30, 120))
        p.employee(employer=old, end=switch - dt.timedelta(days=5))
        new = rng.choice([e for e in EMPLOYERS if e != old])
        p.employee(employer=new, start=switch, salary=rng.uniform(2600, 4200), bonus=False)
        p.goal("job_change", switch)
    else:  # laid off: severance then unemployment benefit
        stop = p.ago(rng.randint(40, 140))
        p.employee(employer=old, end=stop)
        if v % 4 == 1:
            p.add(stop + dt.timedelta(days=10), rng.uniform(6000, 14000), "salary", f"{old} (opzegvergoeding)")
        p.monthly(stop + dt.timedelta(days=30), AS_OF, rng.randint(5, 12), rng.uniform(1300, 1700), "benefit",
                  _pick(p, "HVW uitkering", "ACV werkloosheidsuitkering", "CAPAC allocations", "ABVV werkloosheid",
                        "FGTB chômage"))
        p.goal("job_change", stop)
    p.rent()
    p.life()


def nm_job_change(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(27, 50)
    emp = rng.choice(EMPLOYERS)
    if v == 0:  # payroll provider changed the label, same employer
        cut = p.ago(80)
        p.monthly(p.start, cut, 27, 3100.0, "salary", emp, jitter=0.01)
        p.monthly(cut + dt.timedelta(days=1), AS_OF, 27, 3150.0, "salary", f"SD Worx voor {emp}", jitter=0.01)
    elif v == 1:  # maternity leave: salary paused, mutuality pays, salary back
        p.employee(employer=emp, end=p.ago(170))
        p.monthly(p.ago(165), p.ago(60), 15, 1450.0, "benefit", "CM ziekenfonds (moederschapsrust)")
        p.employee(employer=emp, start=p.ago(45), bonus=False)
        p.kids(1)
    elif v == 2:  # salary paid a few days late in one month
        p.monthly(p.start, AS_OF, 25, 2900.0, "salary", emp, jdays=4)
    elif v == 3:  # promotion: same employer, higher salary
        cut = p.ago(100)
        p.monthly(p.start, AS_OF, 28, lambda d: 3700.0 if d >= cut else 3050.0, "salary", emp)
    else:  # interim worker with weekly payments from the same agency
        d = p.start
        while d <= AS_OF:
            if rng.random() < 0.85:
                p.add(d, rng.uniform(520, 690), "salary", "Randstad Belgium (interim)")
            d += dt.timedelta(days=7)
    p.rent()
    p.life()
    p.near("job_change", p.ago(60))


# ---------- mobility ----------
GARAGES = ["Garage Vanhaecke", "Garage Renault Dupuis", "D'Ieteren Service Center", "Autocentrum Peeters",
           "Garage du Pont SRL", "Euromaster", "Autobedrijf Van Hove"]


def pos_mobility(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(30, 64)
    _salaried(p, _pick(p, "rent", "mortgage"))
    p.car()
    if v % 2 == 0:  # rising garage bills
        g = rng.choice(GARAGES)
        for days, amt in ((330, rng.uniform(250, 400)), (200, rng.uniform(450, 750)), (110, rng.uniform(700, 1200)),
                          (35, rng.uniform(1100, 2100))):
            p.add(p.ago(days, 10), amt, "transport", g)
        if v % 4 == 0:
            p.add(p.ago(20), rng.uniform(55, 80), "transport", _pick(p, "Autokeuring Vlaanderen (herkeuring)", "SBAT contrôle technique"))
        p.goal("mobility", p.ago(35))
    else:  # private lease ending
        end = p.ago(rng.randint(5, 30))
        lessor = _pick(p, "Arval private lease", "LeasePlan", "Athlon Car Lease", "Ayvens", "Alphabet Belgium")
        p.monthly(add_months(end, -48), end, rng.randint(1, 5), rng.uniform(380, 650), "transport", lessor)
        p.add(p.ago(rng.randint(5, 25)), rng.uniform(300, 900), "transport", f"{lessor} (eindafrekening)")
        p.goal("mobility", end)


def nm_mobility(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # one windscreen repair
        p.add(p.ago(30), 640.0, "transport", "Carglass")
    elif v == 1:  # bike repairs rising
        for days, amt in ((300, 45.0), (160, 90.0), (40, 210.0)):
            p.add(p.ago(days), amt, "transport", "Fietsen Vermeiren")
    elif v == 2:  # flat annual service
        for days in (370, 5):
            p.add(p.ago(days), 310.0, "transport", "Garage Vanhaecke (onderhoud)")
    elif v == 3:  # car insurance premium up
        p.car()
        p.add(p.ago(20), 990.0, "insurance_car", "Baloise (premie aanpassing)")
    else:  # company car driver: lease paid by employer, only tolls/parking
        p.b.scatter(p.start, AS_OF, "transport", ["Interparking", "4411 parkeren", "Q-Park"], 3.0, 3, 18)
    p.near("mobility", p.ago(30))


# ---------- first_employee ----------
def pos_first_employee(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(30, 52)
    clients = rng.sample(FREELANCE_CLIENTS, 6)
    p.freelancer(clients[:3], end=p.ago(200), lo=900, hi=2400, per_month=1.6)
    p.freelancer(clients, start=p.ago(199), lo=1500, hi=4200, per_month=3.4, fund="Xerius")
    if v % 2 == 0:
        sub = _pick(p, "Freelancer Yannick Goossens (onderaanneming)", "Sous-traitance Martin SRL",
                    "Onderaannemer Bouw Vercammen", "Tim Peeters BV (subcontracting)")
        for k in range(rng.randint(3, 5)):
            p.add(p.ago(10 + 25 * k, 5), rng.uniform(1200, 3000), "other", sub)
    if v % 3 == 1:
        p.monthly(p.ago(60), AS_OF, 25, rng.uniform(1600, 2400), "other",
                  _pick(p, "Interim Start People (uitzendkracht)", "Partena sociaal secretariaat", "Securex (loonadministratie)"))
    p.rent() if v % 2 else p.mortgage()
    p.life()
    p.goal("first_employee", p.ago(100))


def nm_first_employee(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(32, 55)
    clients = rng.sample(FREELANCE_CLIENTS, 3)
    p.freelancer(clients, lo=1000, hi=2600, per_month=1.6)
    if v == 0:  # accountant fees
        p.monthly(p.start, AS_OF, 10, 160.0, "other", "Boekhouder Fiducia Vanneste")
    elif v == 1:  # one huge project invoice, not growth
        p.add(p.ago(40), 18500.0, "invoice_income", "Gemeente Zemst (aanbesteding)")
    elif v == 2:  # VAT refund inflates income
        p.add_signed(p.ago(30), 3800.0, "other", "FOD Financiën terugbetaling btw")
    elif v == 3:  # pays a cleaning lady via service vouchers
        p.monthly(p.start, AS_OF, 3, 108.0, "other", "Pluxee dienstencheques")
    else:  # occasional co-working + one-off designer payment
        p.monthly(p.start, AS_OF, 1, 220.0, "other", "Coworking Hal 5")
        p.add(p.ago(50), 450.0, "other", "Grafisch ontwerper Lotte V. (logo)")
    p.rent()
    p.life()
    p.near("first_employee", p.ago(60))


# ---------- inheritance ----------
def pos_inheritance(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(38, 72)
    _salaried(p, "mortgage") if p.age < 65 else (p.retiree(), p.life(0.8))
    d = p.ago(rng.randint(5, 80))
    notary = _pick(p, "Notaris Van Rompaey (nalatenschap Verbeke)", "Notaire Grégoire (succession Thiry)",
                   "Notariskantoor De Groote derdenrekening (erfenis)", "Notaris Bosmans - nalatenschap")
    p.add_signed(d, rng.uniform(30000, 220000), "other" if v % 2 else "notary", notary)
    if v % 3 == 0:
        p.add(d - dt.timedelta(days=rng.randint(60, 150)), rng.uniform(3500, 6500), "other",
              _pick(p, "Uitvaartzorg Vandeputte", "Pompes funèbres Delcourt"))
    if v % 3 == 1:
        p.add(d + dt.timedelta(days=3), rng.uniform(2000, 15000), "tax", "Vlabel successierechten")
    p.goal("inheritance", d)


def nm_inheritance(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(40, 70)
    _salaried(p, "mortgage")
    if v == 0:  # sold own flat via the notary
        p.add_signed(p.ago(30), 190000.0, "property", "Notaris Hendrickx (verkoop appartement)")
    elif v == 1:  # insurance claim payout
        p.add_signed(p.ago(25), 24000.0, "other", "AG Insurance (schadevergoeding brand)")
    elif v == 2:  # lottery win
        p.add_signed(p.ago(40), 25000.0, "other", "Nationale Loterij (winst)")
    elif v == 3:  # paid a funeral, no inheritance yet
        p.add(p.ago(45), 5200.0, "other", "Uitvaartzorg Lievens")
    else:  # large group insurance lump sum at 65 (pension capital)
        p.age = 65
        p.add_signed(p.ago(20), 68000.0, "pension", "AG Insurance groepsverzekering (kapitaal)")
    p.near("inheritance", p.ago(30))


# ---------- study_start ----------
SCHOOLS = ["KU Leuven inschrijvingsgeld", "UGent inschrijving", "UCLouvain minerval", "Université de Liège minerval",
           "Arteveldehogeschool", "Thomas More inschrijving", "HOGENT studiegeld", "UAntwerpen inschrijving",
           "Vrije Universiteit Brussel", "HE Vinci minerval"]


def pos_study_start(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(44, 58)
    _salaried(p, "mortgage")
    p.kids(rng.randint(1, 3))
    d = dt.date(2026, rng.choice([8, 9, 9, 10]), rng.randint(1, 28))
    d = min(d, AS_OF)
    p.add(d, rng.choice([1092.10, 1150.0, 835.0, 1121.0, 129.0]), "tuition", SCHOOLS[v % len(SCHOOLS)])
    if v % 2 == 0:
        p.monthly(dt.date(2026, 9, 1), AS_OF, 1, rng.uniform(400, 560), "rent",
                  _pick(p, "Kot Studentenhuis De Waaier", "Kot Mevr. Lauwers", "Kot à Louvain-la-Neuve"))
    if v % 3 == 0:
        p.add(d + dt.timedelta(days=7), rng.uniform(120, 380), "school", _pick(p, "Acco cursusdienst", "Standaard Boekhandel (studieboeken)"))
    p.goal("study_start", d)


def nm_study_start(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # the student pays their own tuition
        p.age = 19
        p.monthly(p.start, AS_OF, 1, 450.0, "allowance_from_parents", "Mama en papa")
        p.b.scatter(p.start, AS_OF, "student_income", ["Studentenjob Colruyt"], 1.0, 80, 300)
        p.add(dt.date(2026, 9, 25), 1092.10, "tuition", "KU Leuven inschrijvingsgeld")
        p.life(0.5)
        p.band = (100, 2500, 800)
    elif v == 1:  # parent paying secondary school
        p.age = 46
        _salaried(p, "mortgage")
        p.kids(2)
        p.add(dt.date(2026, 9, 10), 320.0, "school", "Sint-Jozefscollege schoolrekening")
    elif v == 2:  # adult evening course
        p.age = 36
        _salaried(p, "rent")
        p.add(dt.date(2026, 9, 15), 395.0, "tuition", "Syntra West (avondopleiding)")
    elif v == 3:  # music academy for a child
        p.age = 42
        _salaried(p, "mortgage")
        p.kids(1)
        p.add(dt.date(2026, 9, 5), 75.0, "school", "Academie voor Muziek en Woord")
    else:  # parent of a 3rd-year student, tuition paid a year ago and again now (not a start)
        p.age = 52
        _salaried(p, "mortgage")
        p.add(dt.date(2025, 9, 20), 1092.10, "tuition", "UGent inschrijving")
        p.add(dt.date(2026, 9, 18), 1092.10, "tuition", "UGent inschrijving")
    p.near("study_start", dt.date(2026, 9, 15))


# ---------- side_job ----------
def pos_side_job(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(25, 50)
    _salaried(p, _pick(p, "rent", "mortgage"))
    start = p.ago(rng.randint(40, 160))
    payers = rng.sample(FREELANCE_CLIENTS, rng.randint(1, 2))
    for k in range(rng.randint(2, 5)):
        p.add(start + dt.timedelta(days=15 + 22 * k + rng.randint(0, 6)), rng.uniform(280, 1500), "invoice_income",
              rng.choice(payers))
    if v % 3 != 2:
        loket = _pick(p, "Ondernemingsloket Acerta (inschrijving KBO)", "Ondernemingsloket Xerius (inschrijving KBO)",
                      "Ondernemingsloket Formalis (inschrijving KBO)", "Guichet d'entreprises Securex (inscription BCE)")
        p.add(start, rng.uniform(95, 110), "other", loket)
    fund = _pick(p, "Xerius (bijberoep)", "Liantis (bijberoep)", "Acerta (bijberoep)", "UCM (activité complémentaire)")
    for q in _quarter_days(start, AS_OF, (3, 6, 9, 12), rng):
        p.add(q, rng.uniform(80, 260), "social_contribution", fund)
    if v % 3 == 2:  # no loket payment seen: registered via accountant, contribution only
        p.add(start + dt.timedelta(days=5), rng.uniform(90, 200), "social_contribution", fund)
    p.goal("side_job", start)


def nm_side_job(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # sells second-hand stuff
        p.add_signed(p.ago(30), 185.0, "other", "Vinted uitbetaling")
        p.add_signed(p.ago(70), 60.0, "other", "2dehands.be uitbetaling")
    elif v == 1:  # teacher: exam board fee in summer
        p.add(dt.date(2026, 7, 8), 380.0, "invoice_income", "Examencommissie Vlaamse Gemeenschap")
    elif v == 2:  # lets a studio (landlord income)
        p.monthly(p.start, AS_OF, 2, 640.0, "other", "Huurder Mevr. Desmet (huur studio)")
    elif v == 3:  # Airbnb host now and then
        for d in (40, 95, 150):
            p.add_signed(p.ago(d), rng.uniform(200, 450), "other", "Airbnb payout")
    else:  # football referee fees
        p.monthly(p.ago(240), AS_OF, 20, rng.uniform(60, 140), "other", "KBVB scheidsrechtersvergoeding")
    p.near("side_job", p.ago(40))


# ---------- go_international ----------
FOREIGN = ["Northwind GmbH (DE)", "Studio Lumière SARL (FR)", "Brightline Ltd (UK)", "Kanaal BV (NL)",
           "Atlas Inc (US)", "Fjord Media AS (NO)", "Moselle Conseil SA (LU)", "Rheinwerk AG (DE)",
           "Delta Design BV (NL)", "Maison Garnier SAS (FR)", "Costa Ventures SL (ES)", "Bottega Rossi Srl (IT)"]


def pos_go_international(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(28, 58)
    p.freelancer(lo=1000, hi=3500, per_month=1.6)
    foreign = rng.sample([f for f in FOREIGN if not f.endswith("(NO)")] if v % 3 else FOREIGN, rng.randint(1, 3))
    start = p.ago(rng.randint(40, 200))
    for k in range(rng.randint(2, 5)):
        p.add(start + dt.timedelta(days=20 * k + rng.randint(0, 8)), rng.uniform(1800, 7000), "invoice_income",
              rng.choice(foreign))
    if v % 4 == 0:
        p.add(p.ago(15), rng.uniform(25, 60), "other", _pick(p, "Wise (fx fee)", "Revolut Business"))
    p.rent() if v % 2 else p.mortgage()
    p.life()
    p.goal("go_international", start)


def nm_go_international(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # webshop refund
        _salaried(p, "rent")
        p.add_signed(p.ago(20), 79.95, "other", "Zalando SE (DE) terugbetaling")
    elif v == 1:  # cross-border employee paid by a Luxembourg employer
        p.employee(employer="Cactus SA (LU)", salary=3900)
        p.rent()
        p.life()
    elif v == 2:  # Belgian clients only, one with a (BE) tag
        p.freelancer(["Studio Kwadraat BV (BE)", "Agence Pixelle SRL (BE)", "De Werf vzw"])
        p.rent()
        p.life()
    elif v == 3:  # Amazon refund from LU
        _salaried(p, "rent")
        p.add_signed(p.ago(35), 42.0, "other", "Amazon EU SARL (LU) remboursement")
    else:  # holiday spending abroad
        _salaried(p, "mortgage")
        p.b.scatter(p.ago(60), p.ago(45), "leisure", ["Carrefour Express (FR)", "Restaurant Le Galet (FR)"], 6, 15, 80)
    p.near("go_international", p.ago(30))


# ---------- care_parent ----------
CARE = ["WZC Hof ter Linde (woonzorgcentrum)", "WZC De Linde (woonzorgcentrum)", "WZC Sint-Elisabeth (woonzorgcentrum)",
        "Familiehulp (thuiszorg)", "i-mens (thuisverpleging)", "Wit-Gele Kruis (thuisverpleging)",
        "Résidence Les Tilleuls (maison de repos)", "Solidaris aide familiale (thuiszorg)"]


def pos_care_parent(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(42, 64)
    _salaried(p, "mortgage")
    start = p.ago(rng.randint(50, 220))
    big = CARE[v % len(CARE)]
    amount = rng.uniform(1600, 2300) if "woonzorg" in big or "repos" in big else rng.uniform(180, 520)
    p.monthly(start, AS_OF, rng.randint(3, 15), amount, "healthcare", big, jitter=0.03)
    if v % 3 == 0:
        p.add(start - dt.timedelta(days=rng.randint(10, 40)), rng.uniform(400, 1400), "healthcare",
              _pick(p, "AZ Groeninge (ziekenhuisfactuur)", "Clinique CHC (facture hospitalisation)"))
    p.goal("care_parent", start)


def nm_care_parent(p: P, v: int) -> None:
    rng = p.rng
    if v == 0:  # one hospital bill
        p.age = 52
        _salaried(p, "mortgage")
        p.add(p.ago(30), 980.0, "healthcare", "AZ Groeninge (ziekenhuisfactuur)")
    elif v == 1:  # the customer IS the elderly resident
        p.age = 84
        p.retiree(pension=2400)
        p.monthly(p.ago(200), AS_OF, 5, 1950.0, "healthcare", "WZC De Linde (woonzorgcentrum)")
        p.life(0.4)
        p.band = (2000, 30000, 15000)
        p.start_balance = 20000
    elif v == 2:  # 32-year-old with weekly physio for a sports injury
        p.age = 32
        _salaried(p, "rent")
        p.monthly(p.ago(150), AS_OF, 12, 120.0, "healthcare", "Kinesist Van Dyck")
    elif v == 3:  # parent paying daycare monthly
        p.age = 34
        _salaried(p, "rent")
        p.kids(1)
        p.monthly(p.start, AS_OF, 1, 520.0, "childcare", "Kinderopvang 't Kroostje")
    else:  # 48, own dentist trajectory (orthodontics) monthly
        p.age = 48
        _salaried(p, "mortgage")
        p.monthly(p.ago(240), AS_OF, 18, 150.0, "healthcare", "Orthodontist Dr. Callens")
    p.near("care_parent", p.ago(60))


# ---------- move_house ----------
def pos_move_house(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(23, 45)
    p.employee()
    p.life()
    move = p.ago(rng.randint(20, 120))
    old = rng.choice(LANDLORDS)
    new = rng.choice([l for l in LANDLORDS if l != old])
    old_rent, new_rent = rng.uniform(600, 950), rng.uniform(700, 1200)
    p.rent(old_rent, old, end=move + dt.timedelta(days=5) if v % 2 == 0 else move - dt.timedelta(days=3), day=2)
    p.rent(new_rent, new, start=move, day=4)
    p.add(move - dt.timedelta(days=rng.randint(10, 30)), new_rent * rng.choice([2, 2, 3]), "rent", f"Huurwaarborg {new}")
    if v % 3 != 1:
        p.add(move, rng.uniform(450, 1500), "other", _pick(p, "Verhuisfirma De Kat", "Verhuizingen Peeters",
                                                           "Déménagements Lambotte", "Verhuisfirma Snel & Zorg"))
    if v % 2 == 1:
        p.add(move + dt.timedelta(days=12), rng.uniform(60, 140), "utilities",
              _pick(p, "Engie (nieuw contract)", "Luminus (nieuw contract)", "Fluvius (nieuwe aansluiting)",
                    "Telenet (verhuisservice)"))
    p.start_balance += 3000
    p.goal("move_house", move)


def nm_move_house(p: P, v: int) -> None:
    rng = p.rng
    p.employee()
    p.life()
    landlord = rng.choice(LANDLORDS)
    if v == 0:  # rent indexation with same landlord
        cut = p.ago(50)
        p.monthly(p.start, AS_OF, 3, lambda d: 862.0 if d >= cut else 838.0, "rent", landlord)
    elif v == 1:  # big Ikea purchase
        p.rent(landlord=landlord)
        p.add(p.ago(20), 1350.0, "furniture", "IKEA Gent")
    elif v == 2:  # contract renewal with energy supplier
        p.rent(landlord=landlord)
        p.add(p.ago(15), 0.0 + 35.0, "utilities", "Engie (contractverlenging)")
    elif v == 3:  # helps a friend move: van rental
        p.rent(landlord=landlord)
        p.add(p.ago(25), 120.0, "transport", "Hertz bestelwagen")
    else:  # deposit returned from a parking spot
        p.rent(landlord=landlord)
        p.add_signed(p.ago(30), 150.0, "other", "Terugbetaling waarborg parkeerplaats")
    p.near("move_house", p.ago(40))


# ---------- sell_business ----------
def pos_sell_business(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(56, 66)
    p.start = dt.date(2020, rng.randint(1, 9), 1)
    p.b.start = p.start
    p.freelancer(lo=1500, hi=4500, per_month=2.0)
    p.mortgage() if v % 2 else p.rent()
    p.life()
    d = p.ago(rng.randint(10, 90))
    adv = [_pick(p, "Bedrijfsrevisor Vandaele (waardering)", "Réviseur d'entreprises Dumont (évaluation)",
                 "Bedrijfsrevisor Moore Stephens (waardering)"),
           _pick(p, "Advocatenkantoor Lydian (overdracht)", "Advocatenkantoor Monard (overdracht)",
                 "Cabinet d'avocats Lexia (cession)")]
    p.add(d, rng.uniform(1500, 6000), "other", adv[v % 2])
    if v % 3 == 0:
        p.add(d + dt.timedelta(days=rng.randint(7, 30)), rng.uniform(1200, 4000), "other", adv[(v + 1) % 2])
    p.goal("sell_business", d)


def nm_sell_business(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(55, 64) if v != 2 else 47
    p.start = dt.date(2020, 3, 1)
    p.b.start = p.start
    p.freelancer(lo=1200, hi=3500, per_month=1.8)
    p.rent()
    p.life()
    if v == 0:
        p.monthly(p.start, AS_OF, 12, 180.0, "other", "Boekhouder Verhelst")
    elif v == 1:  # lawyer for debt collection, not a handover
        p.add(p.ago(40), 900.0, "other", "Advocatenkantoor Lydian (incasso)")
    elif v == 2:  # young owner valuing a company to raise capital
        p.add(p.ago(30), 2500.0, "other", "Bedrijfsrevisor Vandaele (kapitaalverhoging)")
    elif v == 3:  # winding down slowly, no advisors
        pass
    else:  # notary for a private will
        p.add(p.ago(60), 520.0, "notary", "Notaris Lievens (testament)")
    p.near("sell_business", p.ago(40))


# ---------- back_on_track ----------
def pos_back_on_track(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(21, 48)
    p.employee(salary=rng.uniform(1700, 2300), bonus=False)
    p.rent(rng.uniform(700, 900))
    p.life(0.9)
    p.band = (-400, 900, 300)
    p.start_balance = 400
    bnpl = _pick(p, "Klarna", "Alma", "Klarna AB", "Alma paiement 4x")
    for m in range(6):
        n = 1 + m // 2 + (v % 2)
        for _ in range(n):
            p.add(p.ago(170 - m * 28 + rng.randint(-5, 5)), rng.uniform(25, 90) * (1 + m * 0.25), "other", bnpl)
    if v % 3 != 2:
        for k in range(rng.randint(1, 3)):
            p.add_signed(p.ago(rng.randint(5, 80)), rng.uniform(40, 160), "other",
                         _pick(p, "Storno domiciliëring Telenet", "Storno domiciliëring Engie", "Storno domiciliëring DKV",
                               "Storno domiciliation Proximus"))
    if v % 3 != 1:
        p.add(p.ago(rng.randint(5, 45)), rng.uniform(120, 650), "other",
              _pick(p, "Gerechtsdeurwaarder Mertens & Co", "Huissier de justice Lambert", "Gerechtsdeurwaarders Dejonghe"))
    p.goal("back_on_track", p.ago(90))


def nm_back_on_track(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # one Klarna payment
        p.add(p.ago(20), 89.0, "other", "Klarna")
    elif v == 1:  # one purchase split in 3 equal payments
        for k in range(3):
            p.add(p.ago(80 - 30 * k), 133.0, "other", "Alma paiement 3x")
    elif v == 2:  # card refund that says storno
        p.add_signed(p.ago(10), 59.0, "other", "Storno kaartbetaling Zalando")
    elif v == 3:  # car loan instalment
        p.monthly(p.start, AS_OF, 10, 310.0, "other", "Cofidis autolening")
    else:  # traffic fine paid
        p.add(p.ago(30), 174.0, "tax", "FOD Justitie verkeersboete")
    p.near("back_on_track", p.ago(30))


# ---------- farm_growth ----------
def pos_farm_growth(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(28, 60)
    buyers = [_pick(p, "BelOrta (veiling)", "Veiling Hoogstraten", "REO Veiling", "Coöperatie Hoogstraten (veiling)"),
              _pick(p, "Milcobel (melkgeld)", "Belgomilk", "Agristo NV", "Clarebout Potatoes")]
    for y, m in [(2025, mm) for mm in range(6, 13)] + [(2026, mm) for mm in range(1, 11)]:
        season = 1.8 if m in (5, 6, 7, 8, 9) else 0.5
        for _ in range(max(0, int(round(rng.gauss(2 * season, 0.6))))):
            d = safe_date(y, m, rng.randint(2, 27))
            p.add(d, rng.uniform(1200, 6500) * (1.25 if (y, m) >= (2026, 1) else 1.0), "invoice_income",
                  buyers[0] if v % 3 else rng.choice(buyers))
    suppliers = ["Aveve", "Agrofront", "Arvesta", "Hendrix Genetics", "SCAR (veevoeder)"]
    p.b.scatter(p.start, AS_OF, "other", suppliers[: 3 + v % 3], 2.0, 250, 2200)
    p.b.yearly(p.start, AS_OF, 2, 10, rng.uniform(150, 260), "other",
               _pick(p, "Boerenbond (lidgeld)", "FWA Fédération Wallonne de l'Agriculture"))
    for q in _quarter_days(p.start, AS_OF, (3, 6, 9, 12), rng):
        p.add(q, rng.uniform(700, 1400), "social_contribution", "Xerius")
    p.mortgage()
    p.life(0.9)
    p.city = _pick(p, "Hoogstraten", "Sint-Katelijne-Waver", "Meulebeke", "Bree", "Ciney")
    p.goal("farm_growth", p.ago(120))


def nm_farm_growth(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, _pick(p, "rent", "mortgage"))
    if v == 0:  # urban garden purchase
        p.add(p.ago(25), 64.0, "other", "Aveve")
    elif v == 1:  # horse owner: feed and stable monthly
        p.monthly(p.start, AS_OF, 7, 95.0, "other", "Aveve (paardenvoer)")
        p.monthly(p.start, AS_OF, 1, 320.0, "leisure", "Manege De Hoefslag")
    elif v == 2:  # garden landscaper freelancer
        p.freelancer(["Tuinen Verlinden BV", "Gemeente Zemst", "Vzw De Kring"])
        p.add(p.ago(30), 410.0, "other", "Aveve")
    elif v == 3:  # retiree still Boerenbond member
        p.add(dt.date(2026, 2, 10), 180.0, "other", "Boerenbond (lidgeld)")
    else:  # bought vegetables at the auction farm shop
        p.add(p.ago(15), 32.0, "groceries", "Veiling Hoogstraten hoevewinkel")
    p.near("farm_growth", p.ago(30))


# ---------- ev_switch ----------
CHARGERS = ["Allego", "Shell Recharge", "Ionity", "Fastned", "Electra", "Blue Corner", "Tesla Supercharger",
            "Powerdale", "TotalEnergies laadpunt"]


def pos_ev_switch(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(28, 62)
    _salaried(p, _pick(p, "rent", "mortgage"))
    first = p.ago(rng.randint(30, 110))
    names = rng.sample(CHARGERS, rng.randint(1, 3)) if v % 2 else [CHARGERS[v % 4]]
    d = first
    while d <= AS_OF:
        p.add(d, rng.uniform(9, 38), "transport", rng.choice(names))
        d += dt.timedelta(days=rng.randint(5, 14))
    if v % 3 == 0:
        p.add(first - dt.timedelta(days=10), rng.uniform(900, 1700), "other",
              _pick(p, "Wallbox installatie Elektro Peeters", "Borne de recharge Elec'Pro"))
    p.goal("ev_switch", first)


def nm_ev_switch(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # one Ionity during a holiday with a rental car
        p.add(dt.date(2026, 8, 3), 42.0, "transport", "Ionity")
        p.add(dt.date(2026, 7, 28), 410.0, "transport", "Sixt autoverhuur")
    elif v == 1:  # e-bike purchase
        p.add(p.ago(40), 2890.0, "transport", "Stromer e-bike Fietsen Janssens")
    elif v == 2:  # shared e-scooters
        p.b.scatter(p.ago(120), AS_OF, "transport", ["Lime", "Bolt", "Dott"], 6, 2, 7)
    elif v == 3:  # charged twice a year ago
        p.add(dt.date(2025, 8, 10), 35.0, "transport", "Fastned")
        p.add(dt.date(2025, 8, 24), 28.0, "transport", "Allego")
    else:  # regular fuel at Shell (not Shell Recharge)
        p.b.scatter(p.ago(120), AS_OF, "transport", ["Shell", "Shell Express"], 3, 45, 85)
    p.near("ev_switch", p.ago(30))


# ---------- first_investment ----------
def pos_first_investment(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(24, 37)
    emp = rng.choice(EMPLOYERS)
    salary = rng.uniform(2700, 3800)
    p.monthly(p.start, AS_OF, 27, salary, "salary", emp, jitter=0.01)
    p.add(dt.date(2025, 12, rng.randint(15, 22)), salary * 0.92, "salary",
          f"{emp} (eindejaarspremie)" if p.lang == "nl" else f"{emp} (prime de fin d'année)")
    p.rent(rng.uniform(650, 850))
    p.life(0.8)
    p.monthly(p.start, AS_OF, 28, rng.uniform(600, 1100), "savings_transfer",
              _pick(p, "KBC Spaarrekening", "Spaarrekening", "Compte épargne"))
    p.band = (1500, 6000, 3500)
    p.goal("first_investment", p.ago(60))


def nm_first_investment(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(26, 36) if v != 2 else 44
    emp = rng.choice(EMPLOYERS)
    p.monthly(p.start, AS_OF, 27, 3300.0, "salary", emp)
    p.add(dt.date(2025, 12, 18), 3000.0, "salary", f"{emp} (eindejaarspremie)")
    p.rent(780.0)
    p.life(0.8)
    p.monthly(p.start, AS_OF, 28, 850.0, "savings_transfer", "KBC Spaarrekening")
    if v == 0:  # saving for a house: property search running
        p.monthly(p.ago(120), AS_OF, 14, 9.99, "subscription", "Immoweb zoekabonnement")
    elif v == 1:  # already invests
        p.products += ["investment_plan"]
        p.monthly(p.start, AS_OF, 5, 150.0, "savings_transfer", "Bolero beleggingsrekening")
    elif v == 2:  # 44
        pass
    elif v == 3:  # saving but also Zimmo search
        p.add(p.ago(30), 19.0, "subscription", "Zimmo alert")
        p.add(p.ago(10), 450.0, "property", "Bouwkundige keuring Vanhove")
    else:  # savings drawn down: big withdrawals
        p.add_signed(p.ago(40), 6000.0, "savings_transfer", "Van spaarrekening")
        p.add(p.ago(38), 6200.0, "other", "Garage Vanhaecke (tweedehandswagen)")
    p.near("first_investment", p.ago(60))


# ---------- together ----------
def pos_together(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(24, 40)
    _salaried(p, "rent")
    partner = rng.choice(NL_FIRST + FR_FIRST) + " " + rng.choice(NL_LAST + FR_LAST)
    if v % 2 == 0:
        start = p.ago(rng.randint(40, 160))
        p.monthly(start, AS_OF, rng.randint(1, 4), rng.uniform(350, 650), "other",
                  f"{partner} (bijdrage huur)" if p.lang == "nl" else f"{partner} (participation loyer)")
        p.goal("together", start)
    else:
        d = p.ago(rng.randint(10, 90))
        p.add(d, rng.uniform(1500, 4500), "other", _pick(p, "Trouwzaal Kasteel Ter Borcht", "Trouwzaal Hof van Lier",
                                                         "Salle de mariage Château de Namur"))
        p.add(d - dt.timedelta(days=rng.randint(30, 90)), rng.uniform(900, 3500), "other",
              _pick(p, "Juwelier Slaets", "Bijouterie Leysen", "Juwelier Goossens"))
        if v % 4 == 1:
            p.add(d + dt.timedelta(days=rng.randint(5, 30)), rng.choice([75.0, 125.0, 150.0]), "other",
                  _pick(p, "Gemeente Lier (huwelijk)", "Gemeente Gent (huwelijk)", "Commune de Wavre (mariage)"))
        p.goal("together", d)


def nm_together(p: P, v: int) -> None:
    rng = p.rng
    _salaried(p, "rent")
    if v == 0:  # December jewellery gift
        p.add(dt.date(2025, 12, 19), 340.0, "other", "Juwelier Slaets")
    elif v == 1:  # flatmate sharing costs
        p.monthly(p.start, AS_OF, 2, 420.0, "other", "Huisgenoot Ruben (gedeelde kosten)")
    elif v == 2:  # wedding guest
        p.add(p.ago(30), 150.0, "other", "Huwelijkslijst Lies & Arne (Casa)")
    elif v == 3:  # parent pays part of the rent
        p.monthly(p.ago(200), AS_OF, 1, 300.0, "allowance_from_parents", "Mama (bijdrage)")
    else:  # watch repair at a jeweller
        p.add(p.ago(45), 85.0, "other", "Juwelier Goossens (herstelling uurwerk)")
    p.near("together", p.ago(40))


# ---------- separation ----------
def pos_separation(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(32, 58)
    p.employee()
    split = p.ago(rng.randint(40, 150))
    if v % 2 == 0:
        p.mortgage()
    else:
        p.rent(rng.uniform(800, 1100))
    p.life()
    p.rent(rng.uniform(650, 950), rng.choice(LANDLORDS), start=split)
    partner = rng.choice(NL_FIRST + FR_FIRST) + " " + p.last
    if v % 3 != 2:
        p.monthly(p.start, split - dt.timedelta(days=10), 26, rng.uniform(900, 1600), "other",
                  f"{partner} (gezamenlijke rekening)" if p.lang == "nl" else f"{partner} (compte commun)")
    p.add(split + dt.timedelta(days=rng.randint(-20, 30)), rng.uniform(600, 2500), "other",
          _pick(p, "Advocaat De Meyer (echtscheiding)", "Bemiddelaar Claessens (scheiding)",
                "Avocat Mathieu (divorce)", "Advocatenkantoor Van Steen (echtscheiding)"))
    p.start_balance += 3000
    p.goal("separation", split)


def nm_separation(p: P, v: int) -> None:
    rng = p.rng
    p.age = rng.randint(40, 58)
    p.employee()
    p.life()
    if v == 0:  # traffic lawyer
        p.rent()
        p.add(p.ago(30), 650.0, "other", "Advocaat Verbist (verkeersboete)")
    elif v == 1:  # mortgage + child's student kot rent
        p.mortgage()
        p.monthly(dt.date(2026, 9, 1), AS_OF, 2, 470.0, "rent", "Kot Studentenhuis De Waaier")
    elif v == 2:  # lawyer for a rent dispute
        p.rent()
        p.add(p.ago(45), 800.0, "other", "Advocaat Pauwels (huurgeschil)")
    elif v == 3:  # partner's transfers stop because they opened a joint account
        p.mortgage()
        p.monthly(p.start, p.ago(90), 26, 1100.0, "other", "Partner Wim (bijdrage)")
    else:  # second home: holiday flat at the coast with its own mortgage-like rent
        p.mortgage()
        p.monthly(p.start, AS_OF, 3, 380.0, "rent", "Vakantieflat Koksijde (garage + berging)")
    p.near("separation", p.ago(40))


# ---------- plain customers (no label) ----------
def plain(p: P, v: int) -> None:
    rng = p.rng
    kind = v % 4
    if kind == 0:
        p.age = rng.randint(25, 45)
        _salaried(p, "rent")
    elif kind == 1:
        p.age = rng.randint(35, 55)
        _salaried(p, "mortgage")
        p.kids(rng.randint(1, 2))
    elif kind == 2:
        p.age = rng.randint(67, 80)
        p.retiree()
        p.life(0.7)
    else:
        p.age = rng.randint(30, 50)
        p.freelancer()
        p.rent()
        p.life()


POSITIVE = {g: globals()[f"pos_{g}"] for g in GOALS}
NEAR_MISS = {g: globals()[f"nm_{g}"] for g in GOALS}
N_POS = 7
N_NEAR = 5
N_PLAIN = 12


def _plan() -> list[tuple[str, Callable[[P, int], None], int]]:
    plan = []
    for g in GOALS:
        plan += [(f"goal:{g}", POSITIVE[g], v) for v in range(N_POS)]
        plan += [(f"near_miss:{g}", NEAR_MISS[g], v) for v in range(N_NEAR)]
    plan += [("plain", plain, v) for v in range(N_PLAIN)]
    return plan


def holdout_customers(seed: int = 7) -> list[tuple[Customer, list[Transaction], float]]:
    """Build the holdout set deterministically. Order is shuffled so ids don't leak the label."""
    plan = _plan()
    order = list(range(len(plan)))
    random.Random(f"holdout-order-{seed}").shuffle(order)
    out = []
    for i, k in enumerate(order):
        label, fn, v = plan[k]
        cid = FIRST_ID + i
        rng = random.Random(f"holdout-{seed}-{label}-{v}")
        p = P(cid, rng, age=rng.randint(28, 55))
        fn(p, v)
        out.append(p.build())
    return out


if __name__ == "__main__":
    from collections import Counter
    data = holdout_customers()
    c = Counter(e["type"].split(":")[0] for cu, _, _ in data for e in cu.ground_truth["events"][:1])
    print(len(data), "customers", dict(c), sum(len(t) for _, t, _ in data), "transactions")
