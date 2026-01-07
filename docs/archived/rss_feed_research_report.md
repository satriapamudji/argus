# RSS Feed Research Report

**Date:** 2026-01-07  
**Purpose:** Evaluate RSS feeds for US market close updates with focus on content extraction reliability  
**Test Method:** `feedparser` for RSS parsing, `newspaper3k` for article content extraction

---

## Executive Summary

| Tier | Description | Feeds Tested | Recommended |
|------|-------------|--------------|-------------|
| **Tier 1** | RSS + Content Extraction Works | 8 | **Yes - Primary sources** |
| **Tier 2** | RSS Works, Content Blocked | 7 | Snippet-only fallback |
| **Tier 3** | RSS Fails | 2 | No |

**Rate Limit Test Results:** All 8 Tier 1 sources passed with **100% success rate** (40/40 articles fetched with 1-second delay).

---

## Rate Limit Test Summary

| Source | Articles Tested | Success Rate | Avg Response Time |
|--------|-----------------|--------------|-------------------|
| CNBC Top News | 5 | 100% (5/5) | 792ms |
| CNBC World | 5 | 100% (5/5) | 581ms |
| CNBC Finance | 5 | 100% (5/5) | 1026ms |
| Nasdaq Markets | 5 | 100% (5/5) | 430ms |
| Nasdaq Earnings | 5 | 100% (5/5) | 799ms |
| Nasdaq Commodities | 5 | 100% (5/5) | 721ms |
| Motley Fool | 5 | 100% (5/5) | 719ms |
| Benzinga | 5 | 100% (5/5) | 2058ms |

**Recommended Rate Limit:** 1 second between requests (tested successfully)

---

## Tier 1: Fully Working Sources (RSS + Content Extraction)

These sources provide both RSS feeds AND allow full article content extraction.

---

### 1. CNBC Top News

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.cnbc.com/id/100003114/device/rss/rss.html` |
| **Status** | 200 |
| **Entry Count** | 30 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 792ms |

#### Article 1

**Title:** Trump says Venezuela to give up to 50 million barrels of oil to U.S.  
**Link:** https://www.cnbc.com/2026/01/06/trump-venezuela-oil.html  
**Authors:** Dan Mangan  
**Publish Date:** 2026-01-06  
**Text Length:** 1,195 chars

**RSS Summary:**
> Trump's announcement came days after U.S. forces attacked Venezuela and captured its leader, Nicolas Maduro, to be prosecuted on drug-trafficking charges.

**Full Extracted Content:**
```
An oil tanker is docked at a pier at the El Palito refinery of the state oil company PDVSA.

President Donald Trump said Tuesday evening that the interim authorities in Venezuela will be turning over between 30 million to 50 million barrels of oil to the United States on the heels of the U.S.'s dramatic ouster of the South American country's authoritarian leader, Nicolas Maduro.

Trump, in a social media post, said the oil will be sold at its market price, "and that money will be controlled by me, as President of the United States of America, to ensure it is used to benefit the people of Venezuela and the United States!"

"I have asked Energy Secretary Chris Wright to execute this plan, immediately," Trump wrote. "It will be taken by storage ships, and brought directly to unloading docks in the United States."

Trump said that the oil being turned over the U.S. was "high quality" and "sanctioned."

U.S. crude futures fell 1.3% to $56.39 per barrel on the heels of Trump's announcement.

The announcement came three days after U.S. forces captured Maduro and his wife in Caracas, and took them to New York, where they are charged in a federal drug-trafficking conspiracy indictment.
```

#### Article 2

**Title:** Berkshire Hathaway lifts new CEO Greg Abel's salary to $25 million  
**Link:** https://www.cnbc.com/2026/01/06/berkshire-hathaway-greg-abel-berkshire-hathaway-ceo-warren-buffet-pay-raise-25-million.html  
**Authors:** Darla Mercado, Cfp  
**Publish Date:** 2026-01-06  
**Text Length:** 1,249 chars

**RSS Summary:**
> Abel took the helm of Berkshire Hathaway on Jan. 1, succeeding legendary investor Warren Buffett.

**Full Extracted Content:**
```
Berkshire Vice Chairman Greg Abel speaks with shareholders during the Berkshire Hathaway Inc. annual shareholders' meeting, in Omaha, Nebraska, U.S., May 2, 2025.

Greg Abel, the newly minted Chief Executive of Berkshire Hathaway , is getting a bump in salary as he takes over from the legendary investor Warren Buffett.

Abel, who began his new role at the conglomerate on Jan. 1, will see his annual cash salary rise to $25 million, according to a Tuesday filing with the U.S. Securities and Exchange Commission. The raise took effect on the same date.

Buffett has championed Abel in his new position. The investor told CNBC's Becky Quick in May that he would rather have Abel handle his money "than any of the top investment advisers or any of the top CEOs in the United States."

"It is a huge endorsement, but it's an endorsement we've made," Buffett told Quick.

Prior to taking the helm at Berkshire, Abel was vice chairman of the company's non-insurance operations. In that post, he earned a salary of $21 million back in 2024, along with "other compensation" of $17,250, according to a 2025 regulatory filing.

Buffett, who was leading Berkshire at the time, had an annual salary of $100,000, plus $305,111 in "other compensation" in 2024.
```

---

### 2. CNBC World

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.cnbc.com/id/100727362/device/rss/rss.html` |
| **Status** | 200 |
| **Entry Count** | 30 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 581ms |

#### Article 1

**Title:** Trump says Venezuela to give up to 50 million barrels of oil to U.S.  
**Link:** https://www.cnbc.com/2026/01/06/trump-venezuela-oil.html  
**Text Length:** 1,195 chars  
**Note:** Same as CNBC Top News (overlap expected - dedupe by URL will handle)

#### Article 2

**Title:** India's state-owned refiners keep buying Russian oil even as New Delhi seeks U.S. tariff relief  
**Link:** https://www.cnbc.com/2026/01/07/india-state-refiners-russian-oil-us-tariffs-ioc-bpcl-psu-mukesh-ambani-reliance-trump.html  
**Authors:** Priyanka Salve  
**Publish Date:** 2026-01-07  
**Text Length:** 2,809 chars

**RSS Summary:**
> India's efforts to secure U.S. tariff relief are being complicated by continued Russian crude purchases by state-owned refiners, offsetting a pullback by private buyers.

**Full Extracted Content:**
```
An oil refinery, operated by Bharat Petroleum Corp., in Mumbai, India.

State-owned refiners in India are still buying Russian oil, even as New Delhi seeks relief from U.S. tariffs imposed for those purchases, according to energy analysts.

The U.S. imposed a "secondary" 25% tariff on Indian goods in August, citing New Delhi's continued imports of Russian crude. Washington also sanctioned Russian oil companies Lukoil and Rosneft in late November.

On Sunday, U.S. Senator Lindsay Graham claimed that India's U.S. ambassador, Vinay Mohan Kwatra, had asked him to urge President Donald Trump to lift these tariffs, arguing that New Delhi has reduced its purchase of Russian oil.

While India's overall demand for Russian crude fell in December, analysts said the decline was largely driven by reduced buying from Mukesh Ambani-owned Reliance Industries , which had been a major importer before the U.S. sanctions on Lukoil and Rosneft took effect in late November.

State-owned refiners, known as public sector undertakings (PSUs), have offset part of that drop for Russian oil, analysts added.

State-owned Indian firms like the IOC (Indian Oil Corporation) and BPCL (Bharat Petroleum Corporation) "have continued to buy Russian crude for future delivery, through non-sanctioned suppliers," said Muyu Xu, senior crude oil analyst at tanker tracker firm Kpler.

BPCL declined to comment, while IOC and Hindustan Petroleum Corporation , as well as the Indian Ministry of Petroleum and Natural Gas did not respond to requests for comment from CNBC.

India has faced sustained pressure from the U.S. to cut back on Russian oil imports, an economic lifeline that enables Moscow to withstand Western economic sanctions over its war against Ukraine.

"Despite declining aggregate imports, PSU refinery intake of Russian crude has remained resilient, highlighting a redistribution rather than a collapse in demand," said Rystad Energy's Pankaj Srivastava...
```

---

### 3. CNBC Finance

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.cnbc.com/id/10000664/device/rss/rss.html` |
| **Status** | 200 |
| **Entry Count** | 30 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 1026ms |

#### Article 1

**Title:** Venezuela could be sitting on a big Bitcoin stash, experts say. Here's what could happen next  
**Link:** https://www.cnbc.com/2026/01/06/venezuela-could-be-sitting-on-a-big-bitcoin-stash-experts-say-heres-what-could-happen-next-.html  
**Authors:** Liz Napolitano  
**Publish Date:** 2026-01-06  
**Text Length:** 5,095 chars

**RSS Summary:**
> Although it's hard to say how much bitcoin could be held by Venezuela, it's likely the regime has amassed considerable holdings of the token, experts said.

**Full Extracted Content:**
```
Sanctions levied against Venezuela restricted the nation's access to financial markets. To work around this, the country likely experimented with cryptocurrencies, experts said. They noted that it's virtually impossible to ascertain the exact amount of bitcoin Venezuela may be sitting on, or where those holdings could be stored, due to the privacy features of the decentralized asset and its underlying technology. However, one thing is clear: If Maduro and his allies have tokens in their coffers, the assets might soon be on the move, they said. And whether those bitcoins are sold, confiscated or exchanged, cryptocurrency holders could feel the impact.

"It's very fair to assume Venezuela had meaningful exposure to bitcoin," said Gui Gomes, founder and CEO of Latin America-based bitcoin firm OranjeBTC. "Given that they were excluded from the global financial system, probably they had gold, bitcoin and some dollars under their mattress."

Venezuela is likely sitting on sizable amounts of the cryptocurrency — a stash that could be worth billions of U.S. dollars, experts told CNBC.

Following President Nicolás Maduro's deposition last weekend, all eyes are on Venezuela and its vast oil reserves . But there's another resource Maduro's regime is believed to have had in abundance — an asset that, if liquidated or seized, would have implications for global financial markets: bitcoin .

Digital publication Project Brazen reported Saturday that Venezuela could hold roughly $60 billion, citing unnamed sources that were not confirmed through blockchain analysis. Such a stash would put the regime among the biggest holders of the crypto in the world, alongside bitcoin treasury firm Strategy .

Data provider Bitcointreasuries.net puts Venezuela's holdings at 240 bitcoin, worth roughly $22 million. To reach this estimate they used data from a blockchain analytics firm that was cited by a media outlet. Based on their rankings, it would the nin...
```

#### Article 2

**Title:** Venezuela bonds are the hottest trade on Wall Street this week. But there are big risks from here  
**Link:** https://www.cnbc.com/2026/01/06/venezuela-bonds-are-the-hottest-trade-on-wall-street-this-week-but-risks-remain.html  
**Authors:** Yun Li  
**Publish Date:** 2026-01-06  
**Text Length:** 2,102 chars

**RSS Summary:**
> Investors are betting that a political transition along with a clearer path to asset recovery could unlock value that has been frozen for nearly a decade.

**Full Extracted Content:**
```
Demonstrators hold a large Venezuelan flag outside the National Assembly, on the day Vice President Delcy Rodriguez was formally sworn in as the country's interim president, as U.S.-deposed President Nicolas Maduro appeared in a New York court after the Trump administration removed him from power, in Caracas, Venezuela Jan. 5, 2026.

Prices on the country's benchmark notes due in October 2026 have surged to about 43 cents on the dollar, more than doubling since August. The rally comes as traders reassess recovery prospects on the distressed securities following the surprise removal of President Nicolas Maduro and a shift in U.S. policy that has opened the door to a potential restructuring of the nation's debt.

Investors are betting that a faster-than-expected political transition along with a clearer path to asset recovery could unlock value that has been frozen for nearly a decade. Venezuela fell into default in late 2017 after failing to make payments on overseas bonds issued by both the government and its state-owned oil producer PDVSA. Fidelity Investments and T. Rowe Price are among the holders that own significant amounts of these defaulted bonds, according to reports.

Donato Guarino, an emerging-market strategist at Citi, said uncertainties remain particularly given lingering questions about the new government's political alignment with Washington.

"To the Trump administration, it's key to extract the oil reserves the Venezuela has at the moment. That means that the GDP of Venezuela will go higher. That means that the ability to pay bondholders will be higher," Guarino told CNBC. "However, in the short term, you may see some risks because what Trump did is a big gamble... there is a question of loyalty of the current new president towards Trump."

Trump has, in recent days, said the U.S. would "run" Venezuela, threatened Colombia and Cuba and renewed his push to acquire Greenland. Those remarks followed a weekend ...
```

---

### 4. Nasdaq Markets

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.nasdaq.com/feed/rssoutbound?category=Markets` |
| **Status** | 200 |
| **Entry Count** | 15 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 430ms |

#### Article 1

**Title:** Elon Musk's XAI Raises $20 Bln Funding, With Backing From Nvidia And Qatar  
**Link:** https://www.nasdaq.com/articles/elon-musks-xai-raises-20-bln-funding-backing-nvidia-and-qatar  
**Authors:** (RTTNews format)  
**Text Length:** 2,424 chars

**RSS Summary:**
> (RTTNews) - Elon Musk's artificial intelligence firm xAI announced that it has raised $20 billion in upsized Series E funding round, exceeding the $15 billion targeted round size, with backing from AI chip major Nvidia Corp. and Qatar.

**Full Extracted Content:**
```
(RTTNews) - Elon Musk's artificial intelligence firm xAI announced that it has raised $20 billion in upsized Series E funding round, exceeding the $15 billion targeted round size, with backing from AI chip major Nvidia Corp. and Qatar.

The company, which aims to rapidly accelerating its progress in building advanced AI, expects the financing to support infrastructure buildout, and to enable the rapid development and deployment of transformative AI products reaching billions of users. The funding will also fuel groundbreaking research advancing xAI's core mission, which is Understanding the Universe.

The company has raised the funds from investors Valor Equity Partners, Stepstone Group, Fidelity Management & Research Company, Qatar Investment Authority, MGX, Baron Capital Group, amongst other key partners.

NVIDIA and Cisco Investments, strategic investors in the round, continue to support xAI in rapidly scaling its compute infrastructure and buildout of the largest GPU clusters in the world.

The AI startup noted that it advanced a multitude of key initiatives in 2025, including Data Centers, Grok 4 Series, Grok Voice, User metrics, Grok Imagine, and Grok on 𝕏.

xAI continues to expand its decisive compute advantage with the world's largest AI supercomputers at Colossus I and II, ending the year with over one million H100 GPU equivalents.

Grok 5 is currently in training, and the firm is focused on launching innovative new consumer and enterprise products that harness the power of Grok, Colossus, and 𝕏.

The firm added that it is hiring aggressively and seeks mission-oriented individuals to focus on making a transformational impact on the future of humanity.

Media reported recently that the latest expanded funding round includes both equity and debt, with Nvidia contributing up to $2 billion to the equity portion of the deal. The deal was said to be structured through a special purpose vehicle designed to acquire Nvidi...
```

#### Article 2

**Title:** AerCap Prices $1.75 Bln Senior Notes Offering At 4.125%, 4.750%  
**Link:** https://www.nasdaq.com/articles/aercap-prices-175-bln-senior-notes-offering-4125-4750  
**Text Length:** 1,029 chars

**RSS Summary:**
> (RTTNews) - AerCap Holdings N.V. (AER), an aviation leasing company, on Wednesday said its wholly owned subsidiaries, AerCap Ireland Capital Designated Activity Co. and AerCap Global Aviation Trust, have priced a senior notes offering totaling $1.75 billion.

**Full Extracted Content:**
```
(RTTNews) - AerCap Holdings N.V. (AER), an aviation leasing company, on Wednesday said its wholly owned subsidiaries, AerCap Ireland Capital Designated Activity Co. and AerCap Global Aviation Trust, have priced a senior notes offering totaling $1.75 billion.

The offering comprises $900 million of 4.125% senior notes due 2029 and $850 million of 4.750% senior notes due 2033, with the notes fully and unconditionally guaranteed on a senior unsecured basis by AerCap and certain other subsidiaries.

The company said that the proceeds will be used for general corporate purposes, including aircraft acquisitions, investments, financing or refinancing of aircraft assets, and repayment of indebtedness.

On Tuesday, AerCap had closed at $147.40, 0.47% cents lesser on the New York Stock Exchange. In the after-market hours, the stock traded 0.31 cents lesser before ending the trade at $147.09.

The views and opinions expressed herein are the views and opinions of the author and do not necessarily reflect those of Nasdaq, Inc.
```

---

### 5. Nasdaq Earnings

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.nasdaq.com/feed/rssoutbound?category=Earnings` |
| **Status** | 200 |
| **Entry Count** | 15 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 799ms |

#### Article 1

**Title:** Pre-Market Earnings Report for January 7, 2026 : ACI, MSM, UNF, APOG  
**Link:** https://www.nasdaq.com/articles/pre-market-earnings-report-january-7-2026-aci-msm-unf-apog  
**Text Length:** 2,679 chars

**RSS Summary:**
> The following companies are expected to report earnings prior to market open on 01/07/2026. Visit our Earnings Calendar for a full list of expected earnings releases.Albertsons Companies, Inc. (ACI)is reporting for the quarter ending November 30, 2025. The consumer company's con...

**Full Extracted Content:**
```
The following companies are expected to report earnings prior to market open on 01/07/2026. Visit our Earnings Calendar for a full list of expected earnings releases.



Albertsons Companies, Inc. (ACI)is reporting for the quarter ending November 30, 2025. The consumer company's consensus earnings per share forecast from the 5 analysts that follow the stock is $0.63. This value represents a 7.35% decrease compared to the same quarter last year. In the past year ACI has beat the expectations every quarter. The highest one was in the 3rd calendar quarter where they beat the consensus by 16.67%. Zacks Investment Research reports that the 2026 Price to Earnings ratio for ACI is 8.59 vs. an industry ratio of 23.80.



MSC Industrial Direct Company, Inc. (MSM)is reporting for the quarter ending November 30, 2025. The industrial services company's consensus earnings per share forecast from the 10 analysts that follow the stock is $0.95. This value represents a 10.47% increase compared to the same quarter last year. In the past year MSM has beat the expectations every quarter. The highest one was in the 3rd calendar quarter where they beat the consensus by 5.83%. Zacks Investment Research reports that the 2026 Price to Earnings ratio for MSM is 20.14 vs. an industry ratio of 64.50.



Unifirst Corporation (UNF)is reporting for the quarter ending November 30, 2025. The uniform company's consensus earnings per share forecast from the 1 analyst that follows the stock is $2.05. This value represents a 14.58% decrease compared to the same quarter last year. In the past year UNF has beat the expectations every quarter. The highest one was in the 3rd calendar quarter where they beat the consensus by 6.05%. Zacks Investment Research reports that the 2026 Price to Earnings ratio for UNF is 27.95 vs. an industry ratio of 22.70, implying that they will have a higher earnings growth than their competitors in the same industry.



Apogee Enterp...
```

#### Article 2

**Title:** After-Hours Earnings Report for January 6, 2026 : AIR, PENG  
**Link:** https://www.nasdaq.com/articles/after-hours-earnings-report-january-6-2026-air-peng  
**Text Length:** 1,511 chars

**Full Extracted Content:**
```
The following companies are expected to report earnings after hours on 01/06/2026. Visit our Earnings Calendar for a full list of expected earnings releases.



AAR Corp. (AIR)is reporting for the quarter ending November 30, 2025. The aerospace and defense company's consensus earnings per share forecast from the 1 analyst that follows the stock is $1.02. This value represents a 13.33% increase compared to the same quarter last year. In the past year AIR has beat the expectations every quarter. The highest one was in the 3rd calendar quarter where they beat the consensus by 10.2%. Zacks Investment Research reports that the 2026 Price to Earnings ratio for AIR is 18.65 vs. an industry ratio of 124.10.



Penguin Solutions, Inc. (PENG)is reporting for the quarter ending November 30, 2025. The internet software company's consensus earnings per share forecast from the 2 analysts that follow the stock is $0.25. This value represents a 19.35% decrease compared to the same quarter last year. In the past year PENG has beat the expectations every quarter. The highest one was in the 3rd calendar quarter where they beat the consensus by 36.36%. Zacks Investment Research reports that the 2026 Price to Earnings ratio for PENG is 15.27 vs. an industry ratio of -24.40, implying that they will have a higher earnings growth than their competitors in the same industry.




The views and opinions expressed herein are the views and opinions of the author and do not necessarily reflect those of Nasdaq, Inc.
```

---

### 6. Nasdaq Commodities

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.nasdaq.com/feed/rssoutbound?category=Commodities` |
| **Status** | 200 |
| **Entry Count** | 15 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 721ms |

#### Article 1

**Title:** Crude Oil Plunges As Traders Assess Impact Of U.S. Offensive In Venezuela  
**Link:** https://www.nasdaq.com/articles/crude-oil-plunges-traders-assess-impact-us-offensive-venezuela  
**Text Length:** 2,908 chars

**RSS Summary:**
> (RTTNews) - Crude oil plummeted on Tuesday, giving away yesterday's gains, as investors resorted to profit-taking while analyzing the consequences of Saturday's swift U.S. military operation in Venezuela on global oil supply along with other geopolitical tensions.

**Full Extracted Content:**
```
(RTTNews) - Crude oil plummeted on Tuesday, giving away yesterday's gains, as investors resorted to profit-taking while analyzing the consequences of Saturday's swift U.S. military operation in Venezuela on global oil supply along with other geopolitical tensions.

WTI Crude Oil for February delivery was last seen trading down by $1.11 (or 1.90%) at $57.21 per barrel.

In a strategically precise military operation, U.S. forces captured the President of Venezuela Nicolas Maduro and his wife on Saturday. They were later produced in a court in New York to be tried for serious criminal charges. During the hearing, the couple pleaded "not guilty."

Saturday's operation was a culmination of a months-long dispute between U.S. President Donald Trump and Maduro, which started after Trump accused Maduro's regime of promoting drug smuggling via U.S. borders into the U.S. soil.

Maduro denied the accusations and claimed that Trump wanted to exploit Venezuela's oil wealth. A founding member of OPEC, Venezuela possesses more oil reserves than each fellow member of the alliance.

After ousting Maduro, Trump announced that the U.S. would be "running" the nation and remarked that U.S. oil majors have now free access to Venezuela's oil.

Contrary to Trump's enthusiasm to hold a monopoly over Venezuela's oil reserves, experts observe that resurrecting Venezuela's destroyed oil infrastructure would require around $100 billion and around a decade's time. As of now, only Chevron operates in Venezuela.

Exxon and ConocoPhillips already lost billions in Venezuela when the then regime nationalized oil production in 2007. It appears that U.S. firms are not in a rush to start production there.

In Syria, government forces clashed with the Syrian Democratic Forces, a group backed by the U.S. and led by the Kurds.

Israel conducted aerial strikes in southern and eastern Lebanon yesterday and today, targeting weapons storage sites owned by the Hez...
```

#### Article 2

**Title:** Gold Advances Amid Geopolitical Tensions, Rate Cut Expectations  
**Link:** https://www.nasdaq.com/articles/gold-advances-amid-geopolitical-tensions-rate-cut-expectations  
**Text Length:** 3,748 chars

**Full Extracted Content:**
```
(RTTNews) - Gold prices moved higher on Tuesday, extending yesterday's gains amid continuing geopolitical conflicts and sustained U.S. Federal Reserve rate cut expectations that drove demand for the yellow metal.

Front Month Comex Gold for January delivery climbed by $45.30 (or 1.02%) to $4,482.20 per troy ounce.

Front Month Comex Silver for January delivery skyrocketed by $4.3660 (or 5.73%) to $80.530 per troy ounce.

Notably, this is a new record high for silver prices, which have increased for three consecutive sessions.

In the U.S. today, the S&P Global Composite PMI recorded 52.7 in December (the lowest in 8 months), while the S&P Global US Services PMI fell to 52.5 in December.

Last Saturday, in a swift and drastic military offensive conducted by the U.S. military on Venezuelan soil, Venezuelan President Nicolas Maduro and his wife were captured and brought to the U.S. to be presented at a New York city courthouse to face drug and weapons charges. During the hearing, the couple pleaded "not guilty."

Maduro's ally Delcy Rodriguez is currently serving as Venezuela's acting president.

U.S. President Donald Trump ,who ordered the operation (termed "Absolute Resolve"), remarked that in the near-term the U.S. would be "running" Venezuela and cautioned the acting regime to cooperate or face a broader military intervention.

Trump's actions follow his months-long accusations against Maduro's regime of promoting narco-and-drug trafficking via U.S. borders into the U.S., causing a huge social crisis. Not only Maduro has refuted Trump's claims, but he counter-alleged that the U.S. wants the rich oil wealth of Venezuela by force.

Trump hinted at a similar operation in Colombia and Mexico if those countries fail to take on their drug cartels. In response, Colombian President Gustavo Petro stated that he would "take up arms" against Trump.

These developments have pushed investors towards gold's safe-haven status...
```

---

### 7. Motley Fool

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.fool.com/feeds/index.aspx` |
| **Status** | 301 (redirect, still works) |
| **Entry Count** | 50 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 719ms |

#### Article 1

**Title:** Is SoundHound AI Stock a Buy Now?  
**Link:** https://www.fool.com/investing/2026/01/07/is-soundhound-ai-stock-a-buy-now/  
**Authors:** Anders Bylund  
**Publish Date:** 2026-01-07  
**Text Length:** 4,365 chars

**RSS Summary:**
> Is SoundHound AI a buy after its recent pullback? The news says yes, even if the stock chart disagrees.

**Full Extracted Content:**
```
Is SoundHound AI a buy after its recent pullback? The news says yes, even if the stock chart disagrees.

I thought SoundHound AI (SOUN +2.09%) was a strong buy in December. As of Jan. 5, the stock price is down 8% from that point, though I've seen nothing but good news around the voice command specialist in that period. Long story short, I'm even more into SoundHound AI's stock nowadays.

SoundHound AI was doing AI before you had a smartphone

As a reminder, SoundHound AI has been developing artificial intelligence (AI) tools for audio analysis for two decades. The original Midomi app, later renamed to SoundHound, identified songs heard by your smartphone's microphones, using the mobile hardware of 2006. The company added more use cases and customers over the years and decided to shoot for commercial success with a cash-raising special purpose acquisition company (SPAC) merger in 2022.

The stock soared in 2024, as AI giant Nvidia (NVDA 0.47%) made a small investment in SoundHound AI stock. More to the point, Nvidia CEO Jensen Huang has been serving business tips to SoundHound AI leader Keyvan Mohajer for about 10 years. And the two companies are working together, developing voice control systems on Nvidia hardware that can do their job without an active internet connection.

You should also know that SoundHound AI's low-key financial results are about to change. The company has a deep backlog of long-term contracts that should deliver more than $1.2 billion of revenue over the next seven years. At the same time, the backlog itself is growing quickly. February's Q4 2025 report should come with an updated backlog figure, and I expect some serious growth in this indicator of future sales and profits.

Good news, bad stock chart -- what gives?

That's old news, of course. SoundHound AI investors saw the Nvidia connection years ago, and the order backlog is well known.

Advertisement

Yet SoundHound AI's stock has fallen 38% ...
```

#### Article 2

**Title:** 3 Top Quantum Computing Stocks to Buy in 2026  
**Link:** https://www.fool.com/investing/2026/01/07/3-top-quantum-computing-stocks-to-buy-in-2026/  
**Authors:** Justin Pope  
**Publish Date:** 2026-01-07  
**Text Length:** 5,342 chars

**Full Extracted Content:**
```
Investing in quantum computing doesn't have to feel like playing the lottery. There are proven winners with exposure to quantum computing worth buying and holding right now.

It's still early, but quantum computing appears to be another significant leap forward in technological innovation. Quantum computers utilize the laws of physics to perform complex calculations exponentially faster than even today's supercomputers can.

Researchers at McKinsey & Company anticipate that quantum computing can grow to a $100 billion market over the next decade, and who knows where it will go from there.

Investors have poured into several pure-play quantum computing stocks, but companies like IonQ and D-Wave Quantum currently generate little revenue and have already risen to sky-high valuations. However, investing in quantum computing doesn't need to be an all-or-nothing gamble.

Here are three companies with established and successful businesses that also deal in quantum computing. Consider buying them as top quantum computing stocks for 2026.

1. Nvidia

The explosive growth in artificial intelligence (AI) has rocketed Nvidia (NVDA 0.47%) to the top of the technology world as the leader in GPU chips used in data centers for AI workloads. Quantum computing could become a key stepping stone to more advanced AI over the coming years as computing power demands continue to increase.

Advertisement

Nvidia wouldn't want to be on the outside of quantum computing if it began displacing traditional GPUs, so the company has a clear interest in exploring quantum technology. It has developed NVQLink, which enables quantum processors to work with AI supercomputers, as well as CUDA-Q, an open-source development platform for quantum systems and applications.

Expand NASDAQ : NVDA Nvidia Today's Change ( -0.47 %) $ -0.88 Current Price $ 187.24 Key Data Points Market Cap $4.5T Day's Range $ 186.82 - $ 192.17 52wk Range $ 86.62 - $ 212.19 Volume 177M A...
```

---

### 8. Benzinga

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.benzinga.com/feed` |
| **Status** | 200 |
| **Entry Count** | 10 |
| **Extraction** | ✅ SUCCESS |
| **Rate Limit Test** | 5/5 passed, avg 2058ms |

**⚠️ WARNING:** Benzinga articles are predominantly "listicle" style guides (e.g., "Best AI Trading Bots", "Best Portfolio Trackers") rather than breaking news. This may require topic filtering for market update use cases.

#### Article 1

**Title:** Best AI Stock Trading Bots and Software in January 2026  
**Link:** https://www.benzinga.com/money/best-ai-stock-trading-bots-software  
**Authors:** Ryan Peterson  
**Text Length:** 9,887 chars

**Full Extracted Content:**
```
Artificial intelligence is reshaping how individuals and institutions trade. From real-time signal analysis to adaptive strategies that evolve with the market, AI trading bots are giving investors access to tools that were once reserved for hedge funds and quant teams. These platforms can automate strategies, eliminate emotional trading and help identify patterns hidden in the data all with minimal manual intervention.

AI stock trading bots and software combine automation with machine learning or algorithmic adaptability to help users execute trades more efficiently.

How We Chose the Best AI Trading Bots

To identify the best AI-powered trading platforms, we considered the following:

Artificial intelligence or machine learning capabilities : Does the software learn and adapt over time?

: Does the software learn and adapt over time? Automation and execution : Can the bot place trades automatically or does it rely on alerts?

: Can the bot place trades automatically or does it rely on alerts? Strategy customization : Can users personalize or optimize trading approaches?

: Can users personalize or optimize trading approaches? Supported markets and brokers : Does it integrate with major stock or crypto exchanges?

: Does it integrate with major stock or crypto exchanges? Pricing transparency and customer trust: Is the platform credible and are costs clear?

This list includes platforms that apply AI not just for automation but for decision-making, pattern recognition and continuous learning.

6 Best AI Stock Trading Bots and Software

Here are 6 top AI-powered trading platforms that combine automation with intelligent strategy optimization to help investors make faster, more informed trading decisions.

1. Best All-in-One AI Trading Bot: Cryptohopper

Cryptohopper is one of the most advanced AI trading platforms for retail investors, supporting multiple exchanges and a growing list of AI-powered features. Its Alg...
```

#### Article 2

**Title:** Best Stock Portfolio Trackers in January 2026  
**Link:** https://www.benzinga.com/money/best-portfolio-tracker  
**Authors:** Dan Schmidt  
**Text Length:** 25,237 chars

**Note:** Very long listicle-style content. May not be suitable for news digest use case.

---

## Tier 2: RSS Works, Content Extraction Blocked

These sources provide RSS feeds with summaries, but block direct article scraping. **Use RSS summary only.**

### 1. MarketWatch Top Stories

| Property | Value |
|----------|-------|
| **RSS URL** | `https://feeds.content.dowjones.io/public/rss/mw_topstories` |
| **Status** | 200 |
| **Entry Count** | 10 |
| **Extraction** | ❌ FAILED (401 Forbidden) |

**Sample RSS Summaries (USABLE):**

1. **Trump says Venezuela will send U.S. up to 50 million barrels of oil — and he'll control the proceeds**
   > President Donald Trump late Tuesday said Venezuela will send the U.S. 30 million to 50 million barrels of oil, which will then be sold by the U.S. and the proceeds controlled by him.

2. **As Tesla's stock falls, Elon Musk brushes off Nvidia's competitive threat**
   > Nvidia is ramping up its work on driverless vehicle technology, a field dominated by Tesla and a few other players. But Musk doesn't see an imminent reason to worry.

---

### 2. MarketWatch Real-time Headlines

| Property | Value |
|----------|-------|
| **RSS URL** | `https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines` |
| **Status** | 200 |
| **Entry Count** | 10 |
| **Extraction** | ❌ FAILED (401 Forbidden) |
| **RSS Summary** | ⚠️ **NO SUMMARY PROVIDED** |

**Not Recommended:** Headlines only, no content.

---

### 3. Bloomberg Markets

| Property | Value |
|----------|-------|
| **RSS URL** | `https://feeds.bloomberg.com/markets/news.rss` |
| **Status** | 200 |
| **Entry Count** | 30 |
| **Extraction** | ❌ FAILED (403 Forbidden) |

**Sample RSS Summaries (USABLE):**

1. **Asian Rare Earth Stocks Surge on New China-Japan Export Curbs**
   > Rare earth-related shares gained across the Asia-Pacific region after China imposed a ban on exports of military-use items to Japan, a move with the potential to squeeze supply chains.

2. **Botched Debutant Trade Triggers Halt in Sri Lankan Stocks**
   > The Colombo Stock Exchange halted market-wide trading in a rare such move early Wednesday after noticing "unusual" prices in a debutant's shares.

---

### 4. WSJ Markets

| Property | Value |
|----------|-------|
| **RSS URL** | `https://feeds.a.dj.com/rss/RSSMarketsMain.xml` |
| **Status** | 200 |
| **Entry Count** | 20 |
| **Extraction** | ❌ FAILED (403 Forbidden) |

**Sample RSS Summaries (USABLE):**

1. **Stocks Sink in Broad AI Rout Sparked by China's DeepSeek**
   > U.S. stocks were mostly lower, with the Nasdaq leading declines as makers of AI infrastructure suffered steep falls, many in the double digits. Nvidia was down 16%.

2. **Comex Gold, Silver Settle Lower**
   > Gold settled 1.4% lower, down two of the past three sessions, and silver fell 2.5%, down three of the past four sessions.

---

### 5. Seeking Alpha

| Property | Value |
|----------|-------|
| **RSS URL** | `https://seekingalpha.com/market_currents.xml` |
| **Status** | 200 |
| **Entry Count** | 7 |
| **Extraction** | ❌ BLOCKED (returns anti-bot message) |
| **RSS Summary** | ⚠️ **NO SUMMARY PROVIDED** |

**Not Recommended:** Headlines only, bot protection.

---

### 6. Financial Times

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.ft.com/rss/home` |
| **Status** | 301 |
| **Entry Count** | 10 |
| **Extraction** | ❌ BLOCKED (only 161 chars - paywall teaser) |

**Sample RSS Summaries (USABLE):**

1. **Trump says Venezuela will turn over oil to US**
   > President says he will control money earned from sale of up to 50mn barrels of sanctioned crude

2. **Hedge funds hunt for Venezuela's unpaid financial claims**
   > US capture of strongman Nicolás Maduro lifts hopes that country will make good on some debt

---

### 7. Investing.com

| Property | Value |
|----------|-------|
| **RSS URL** | `https://www.investing.com/rss/news.rss` |
| **Status** | 200 |
| **Entry Count** | 10 |
| **Extraction** | ❌ FAILED (403 Forbidden) |
| **RSS Summary** | ⚠️ **NO SUMMARY PROVIDED** |

**Not Recommended:** No summaries, content blocked.

---

## Tier 3: RSS Fails (Not Usable)

| Source | RSS URL | Issue |
|--------|---------|-------|
| Reuters | `https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best` | 301 redirect, 0 entries |
| AP News | `https://rsshub.app/apnews/topics/business` | 403 Forbidden |

---

## Recommendations

### Primary Sources (Tier 1 - Use These)

| Source | RSS URL | Why |
|--------|---------|-----|
| **CNBC Top News** | `https://www.cnbc.com/id/100003114/device/rss/rss.html` | Best overall - 30 entries, full extraction, good summaries |
| **Nasdaq Markets** | `https://www.nasdaq.com/feed/rssoutbound?category=Markets` | Market-focused, RTTNews wire content, fastest response |
| **Nasdaq Earnings** | `https://www.nasdaq.com/feed/rssoutbound?category=Earnings` | Earnings calendar coverage |
| **Nasdaq Commodities** | `https://www.nasdaq.com/feed/rssoutbound?category=Commodities` | Commodity price movements |
| **Motley Fool** | `https://www.fool.com/feeds/index.aspx` | Stock analysis, longer-form content |

### Use With Caution

| Source | RSS URL | Issue |
|--------|---------|-------|
| **Benzinga** | `https://www.benzinga.com/feed` | Mostly listicle content, not breaking news |
| **CNBC World** | `https://www.cnbc.com/id/100727362/device/rss/rss.html` | High overlap with CNBC Top News |
| **CNBC Finance** | `https://www.cnbc.com/id/10000664/device/rss/rss.html` | May overlap with Top News |

### Secondary Sources (Tier 2 - Snippet Only)

| Source | RSS URL | Notes |
|--------|---------|-------|
| **MarketWatch Top Stories** | `https://feeds.content.dowjones.io/public/rss/mw_topstories` | Good summaries (~180 chars), no full text |
| **Bloomberg Markets** | `https://feeds.bloomberg.com/markets/news.rss` | Good summaries, no full text |
| **WSJ Markets** | `https://feeds.a.dj.com/rss/RSSMarketsMain.xml` | Good summaries, no full text |

### Not Recommended

| Source | Reason |
|--------|--------|
| MarketWatch Real-time | No summaries |
| Seeking Alpha | No summaries, bot protection |
| Investing.com | No summaries, 403 blocked |
| Financial Times | Paywall teaser only |

---

## Proposed `rss/us_close_basic.txt`

```
# Primary sources - full content extraction works
https://www.cnbc.com/id/100003114/device/rss/rss.html
https://www.nasdaq.com/feed/rssoutbound?category=Markets
https://www.nasdaq.com/feed/rssoutbound?category=Earnings
https://www.nasdaq.com/feed/rssoutbound?category=Commodities
https://www.fool.com/feeds/index.aspx

# Optional - has overlap with Top News
# https://www.cnbc.com/id/100727362/device/rss/rss.html
# https://www.cnbc.com/id/10000664/device/rss/rss.html

# Use with caution - mostly listicle content
# https://www.benzinga.com/feed

# Secondary sources - snippet only (content extraction blocked)
# https://feeds.content.dowjones.io/public/rss/mw_topstories
# https://feeds.bloomberg.com/markets/news.rss
# https://feeds.a.dj.com/rss/RSSMarketsMain.xml
```

---

## Detailed Rate Limit Test Results

### CNBC Top News
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Trump says Venezuela to give up to 50 million barr... | OK | 1,195 | 912ms |
| 2 | Berkshire Hathaway lifts new CEO Greg Abel's salar... | OK | 1,249 | 841ms |
| 3 | Seven U.S. troops injured in Venezuela raid that c... | OK | 2,009 | 551ms |
| 4 | Trump administration freezes $10B in child, family... | OK | 2,966 | 1,097ms |
| 5 | Prediction markets show rising odds Trump seizes P... | OK | 1,548 | 561ms |

### CNBC World
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Trump says Venezuela to give up to 50 million barr... | OK | 1,195 | 576ms |
| 2 | India's state-owned refiners keep buying Russian o... | OK | 2,809 | 577ms |
| 3 | CNBC's UK Exchange newsletter: Is Britain back? Fi... | OK | 6,696 | 593ms |
| 4 | Trump weighs using U.S. military to acquire Greenl... | OK | 2,980 | 576ms |
| 5 | European markets head for mixed open as Greenland ... | OK | 1,434 | 584ms |

### CNBC Finance
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Venezuela could be sitting on a big Bitcoin stash,... | OK | 5,095 | 567ms |
| 2 | Venezuela bonds are the hottest trade on Wall Stre... | OK | 2,102 | 542ms |
| 3 | Michael Burry's big play off the U.S.-Venezuela si... | OK | 2,505 | 974ms |
| 4 | JPMorgan forms special advisory group to share som... | OK | 2,546 | 1,428ms |
| 5 | Minneapolis Fed's Kashkari indicates interest rate... | OK | 3,065 | 1,618ms |

### Nasdaq Markets
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Berkshire Hathaway Raises CEO Greg Abel's Pay To $... | OK | 576 | 356ms |
| 2 | Air Transat Pilots Ratify New Five-Year Agreement ... | OK | 715 | 593ms |
| 3 | Elon Musk's XAI Raises $20 Bln Funding, With Backi... | OK | 2,424 | 346ms |
| 4 | AerCap Prices $1.75 Bln Senior Notes Offering At 4... | OK | 1,029 | 391ms |
| 5 | Is SoundHound AI Stock a Buy Now? | OK | 4,791 | 463ms |

### Nasdaq Earnings
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Pre-Market Earnings Report for January 7, 2026 : ... | OK | 2,679 | 465ms |
| 2 | After-Hours Earnings Report for January 6, 2026 : ... | OK | 1,511 | 491ms |
| 3 | Pre-Market Earnings Report for January 6, 2026 : ... | OK | 869 | 880ms |
| 4 | What a "Normal" Economy Could Mean for T... | OK | 5,879 | 1,087ms |
| 5 | Bullseye Bounce: Toms Capital Takes a Stake in Tar... | OK | 8,186 | 1,075ms |

### Nasdaq Commodities
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Crude Oil Plunges As Traders Assess Impact Of U.S.... | OK | 2,908 | 459ms |
| 2 | Gold Advances Amid Geopolitical Tensions, Rate Cut... | OK | 3,748 | 452ms |
| 3 | Gold Hovers Near One-week High On Dollar Weakness | OK | 1,900 | 482ms |
| 4 | Oil Extends Gains In Choppy Trade | OK | 1,635 | 1,176ms |
| 5 | Ramaco Resources (METC) Shares Cross Above 200 DMA | OK | 763 | 1,035ms |

### Motley Fool
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Is SoundHound AI Stock a Buy Now? | OK | 4,365 | 388ms |
| 2 | 3 Top Quantum Computing Stocks to Buy in 2026 | OK | 5,343 | 874ms |
| 3 | Bloom Energy vs. Plug Power: Which One Will Domina... | OK | 2,727 | 985ms |
| 4 | 90% of Investors Plan to Own AI Stocks in 2026: He... | OK | 4,978 | 696ms |
| 5 | Warren Buffett's Partner, Charlie Munger, Put Almo... | OK | 4,946 | 654ms |

### Benzinga
| # | Title | Status | Length | Response Time |
|---|-------|--------|--------|---------------|
| 1 | Best AI Stock Trading Bots and Software in January... | OK | 9,887 | 1,254ms |
| 2 | Best Stock Portfolio Trackers in January 2026 | OK | 25,237 | 1,245ms |
| 3 | Best Investing Apps for College Students in Januar... | OK | 12,126 | 2,686ms |
| 4 | Best Binary Options Brokers in January 2026 | OK | 12,526 | 2,820ms |
| 5 | Best ETF Brokers in January 2026 | OK | 13,931 | 2,287ms |

---

## Content Quality Observations

### Issues Noted

1. **Benzinga** - All 5 test articles are "Best X in January 2026" listicle style. **Not suitable for breaking news.** Consider removing or adding topic filter.

2. **Motley Fool** - Opinion/analysis heavy. Good for context but not breaking news.

3. **Nasdaq** - Uses RTTNews wire format. Content is factual but sometimes repetitive phrasing.

4. **CNBC** - Best balance of breaking news + context. Most reliable for US market close updates.

### Overlap Detection

- CNBC Top News and CNBC World have overlapping articles (same Venezuela story appeared in both)
- Dedupe by URL hash will handle this

---

## Next Steps

1. ✅ Review this report
2. ⏳ Confirm source selection
3. ⏳ Populate `rss/us_close_basic.txt` with approved feeds
4. ⏳ Test `argus ingest` with live feeds

---

*Report generated: 2026-01-07 15:00 SGT*  
*Full content samples and rate limit tests included*
