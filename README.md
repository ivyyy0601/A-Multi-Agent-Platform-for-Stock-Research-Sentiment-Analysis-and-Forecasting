#  A Multi-Agent Platform for Stock Research, Sentiment Analysis, and Forecasting

## 1. Project Overview

IvyTrader is an automated stock research and analysis platform built around a clear theme:

- integrating price data, news, social sentiment, machine learning forecasts, LLM-based analysis, multi-agent decision making, and automation into one system

The platform is not only designed to answer:

- whether a stock may move up or down

It is also designed to answer:

- what has been happening recently
- which signals are driving the price
- whether different sources agree with each other
- why the system is leaning bullish or bearish
- how multiple perspectives can be combined into a more complete research conclusion

As a result, IvyTrader is not just a forecasting tool.  
It is a:

- data-driven
- research-oriented
- automation-enabled
- prediction-and-explanation platform

for stock analysis.

---

## 2. Page Overview

This platform is organized around several pages, and each page has a different role in the workflow.

### 2.1 Detail Page

The `Detail` page is the main news-driven analysis page for a single ticker.

On this page, the user can:

- choose a ticker
- change the chart time range
- click one day to open `Day News`
- select multiple days to open `Range News`
- use `Ask AI` to summarize a selected period
- open `AI Deep Analysis` for a single article

From this page, the user gets:

- price action and candlestick history
- related news and Reddit-linked content
- positive, negative, and neutral sentiment labels
- a short-term forecast with confidence
- top drivers behind the prediction
- similar historical periods and what happened afterward
- key impact news and AI-generated explanations

### 2.2 Social Page

The `Social` page is the sentiment-driven prediction page.

On this page, the user can:

- choose a ticker
- switch between `Sentiment`, `Buzz`, and `Bullish %`
- review cross-platform signals from Reddit, Twitter, and News
- inspect similar historical sentiment setups

From this page, the user gets:

- a short-term bullish or bearish prediction
- signal breakdown from the ML model, similar history, and combined output
- current platform sentiment and buzz
- top drivers behind the social prediction
- similar historical days and their later returns
- a final multi-signal summary

### 2.3 Sentiment Page

The `Sentiment` page is the visualization layer for sentiment data itself.

On this page, the user can:

- inspect sentiment trends over time
- compare platforms
- review how sentiment and activity change across dates

From this page, the user gets:

- a direct view of sentiment behavior
- platform-level comparisons
- a cleaner understanding of how sentiment changes before looking at forecasts

### 2.4 Analysis Page

The `Analysis` page is the LLM-based interpretation layer.

On this page, the user can:

- review integrated stock analysis
- read research-style summaries generated from prepared system signals
- inspect outputs that combine data from multiple modules

From this page, the user gets:

- a higher-level explanation built from price, news, sentiment, and model outputs
- a research-style report instead of only a raw prediction
- a more complete view of the ticker across multiple signals

### 2.5 Team Page

The `Team` page is the multi-agent decision layer.

On this page, the user can:

- see multiple agents analyze the same ticker from different roles
- review each agent's opinion
- read the final combined decision-style output

From this page, the user gets:

- a multi-perspective discussion process
- different reasoning styles for the same ticker
- a final manager-style conclusion after the agents are combined

### 2.6 Ops Page

The `Ops` page is the automation and pipeline control layer.

On this page, the user can:

- monitor pipeline status
- see which step is currently running
- review recent automation runs
- manually trigger `Daily Update`
- manually trigger `Batch Collect`

From this page, the user gets:

- visibility into data ingestion, model training, and forecast generation
- confirmation that the system is actively updating
- a manual control surface for the full automated workflow

---

## 3. Core Objectives

This project is built around four main goals.

### 3.1 Build a multi-source research framework

Bring price data, news, and social sentiment into the same system instead of treating them as separate streams.

### 3.2 Create two forecasting pipelines

Use two different perspectives to analyze every ticker:

- `Detail`: more news-driven
- `Social`: more sentiment-driven

### 3.3 Add an LLM interpretation layer

Allow the system not only to generate signals, but also to explain and organize them into a more research-style output.

### 3.4 Build an automated update and training workflow

Turn data updates, model training, forecast generation, and monitoring into a continuous automated loop.

---

## 4. Data System

The IvyTrader data system is built on three main categories.

### 4.1 Price data

Price data is centered around OHLC:

- open
- high
- low
- close
- volume

This is the foundation for technical indicators and price-action analysis.

### 4.2 News data

News data comes from multiple sources and is aligned into a unified structure.  
It is used to:

- identify important events
- analyze news sentiment
- measure article density and trend changes

### 4.3 Social sentiment data

Social sentiment data mainly comes from:

- Reddit
- Twitter
- aggregated news sentiment sources

This data is transformed into structured daily signals such as:

- sentiment
- buzz
- bullish / bearish ratio

This makes it suitable for daily analysis and modeling.

---

## 5. Data Processing Workflow

Before anything reaches the models or the user interface, the system goes through a unified data processing workflow.

### 5.1 Data collection

The platform continuously collects:

- stock price data
- news data
- social and aggregated sentiment data

### 5.2 Data cleaning and filtering

Raw content is transformed into cleaner and more structured data.  
The main focus is on:

- ticker relevance
- sentiment labeling
- date alignment

### 5.3 Daily aggregation

Both news and social content are ultimately transformed into:

- ticker-level
- date-level

daily features

This step makes it possible to place news, sentiment, and price data on the same time scale for:

- machine learning training
- historical lookback
- page-level analysis

---

## 6. System Structure

IvyTrader currently consists of six major pages or modules:

1. `Detail`
2. `Social`
3. `Sentiment`
4. `Analysis`
5. `Team`
6. `Ops`

Together, they form a full structure that moves from data, to prediction, to explanation, to decision support.

---

## 7. Detail: News-Driven Analysis Page

The `Detail` page is the part of the platform that comes closest to a single-stock research terminal.  
Its main purpose is:

- to place price action, related news, model forecasts, and explanations on the same page

### 7.1 Data used in Detail

The `Detail` page combines:

- price action
- technical indicators
- aligned news
- news sentiment and summaries
- similar historical periods

### 7.2 Method used in Detail

The forecasting layer in `Detail` uses machine learning to estimate:

- short-term direction
- medium-term direction

It does not only output a direction.  
It also adds several explanation layers to make the result easier to understand.

### 7.3 Main functions of the Detail page

#### Price chart

The candlestick chart on the left shows price movement.  
It also overlays news markers so the user can observe the relationship between:

- price changes
- and news events

#### Day News

By clicking on a single day, the user can enter the `Day News` view and study:

- what relevant content appeared that day
- what the sentiment looked like
- whether price and information moved together

#### Range News

By selecting a time range, the user can enter `Range News` and study:

- what happened during that period
- whether the move was driven by a chain of events

#### Ask AI

`Ask AI` summarizes the currently selected range and helps explain:

- why the price moved the way it did
- which events mattered most
- what the main drivers were

#### Forecast

The right side of the page shows the short-term forecast, including:

- bullish / bearish
- confidence
- the date the result is based on

#### Top Drivers

This section explains which factors are contributing most to the forecast.

#### Similar Historical Periods

This section finds the most similar historical periods and shows what happened afterward.

#### Key Impact News

This section highlights the most important recent news so the user can quickly identify major events.

#### AI Deep Analysis

This feature analyzes a single news item in more detail and explains:

- why it matters
- whether it is more bullish or bearish

### 7.4 Positioning of Detail

The `Detail` page is best suited for questions like:

- what has happened recently
- why the stock moved the way it did
- why the system is leaning bullish or bearish

It is one of the most complete single-stock research pages in the project.

---

## 8. Social: Sentiment-Driven Forecast Page

The `Social` page is the second major forecasting pipeline and complements `Detail`.  
Instead of focusing on individual news events, it focuses on:

- aggregated sentiment
- discussion intensity
- cross-platform agreement

### 8.1 Data used in Social

The `Social` page mainly reads:

- Reddit sentiment
- Twitter sentiment
- News sentiment
- buzz
- bullish / bearish ratios
- selected technical indicators

### 8.2 Method used in Social

The `Social` page uses a separate machine learning pipeline for short-term direction.  
Its focus is on:

- whether market mood is bullish or bearish
- whether multiple platforms agree
- how similar sentiment setups behaved historically

### 8.3 Main functions of the Social page

#### Price + Sentiment Chart

This chart places price and sentiment on the same timeline.  
The user can switch between:

- `Sentiment`
- `Buzz`
- `Bullish %`

#### Current Prediction

This section shows:

- bullish / bearish
- confidence
- forecast date
- target date

#### Signal Breakdown

This section separates the result into:

- the machine learning model
- similar history
- the combined signal

#### Platform Sentiment Now

This section shows the current sentiment and buzz for:

- Reddit
- Twitter
- News

#### Top Drivers

This section shows which sentiment or technical features are pushing the result most strongly.

#### Similar Days

This section finds the most similar historical sentiment setups and shows:

- similarity scores
- what happened afterward

#### Multi-signal Summary

This section provides the final overall judgment after combining all available signals.

### 8.4 Positioning of Social

The `Social` page is best suited for questions like:

- what the current market mood looks like
- whether sentiment is aligned across platforms
- what similar sentiment setups have implied in the past

It is therefore a sentiment-driven short-term forecast page.

---

## 9. Sentiment: Sentiment Visualization Page

The `Sentiment` page is designed primarily to visualize sentiment data itself.

It emphasizes:

- charts
- trend observation
- platform comparison

rather than full prediction output.

### 9.1 Main role of the Sentiment page

It is useful for:

- observing whether sentiment is strengthening or weakening
- comparing sentiment trends across platforms
- visually studying the relationship between sentiment and market behavior

### 9.2 Positioning of Sentiment

If:

- `Social` = sentiment + forecasting

Then:

- `Sentiment` = sentiment data visualization

---

## 10. Analysis: LLM-Based Interpretation Layer

The `Analysis` page serves as the interpretation layer of the platform.  
It does not retrain models.  
Instead, it:

- reads the structured signals already prepared by the system
- uses an LLM to organize them into a higher-level explanation

### 10.1 What Analysis reads

The page reads signals such as:

- price and technical data
- news information
- sentiment data
- forecast outputs

### 10.2 What Analysis produces

It produces:

- a more integrated research view
- more report-like summaries
- explanations that connect multiple signals together

### 10.3 Positioning of Analysis

Compared with `Detail` and `Social`, which each focus on one main perspective, `Analysis` is better understood as:

- a combined research page

Its purpose is to read existing signals and explain them clearly.

---

## 11. AI Agent: Integrated Analysis Layer

On top of `Analysis`, the project also introduces:

- AI Agent

### 11.1 Role of the AI Agent

The AI Agent acts like:

- an analyst reading a prepared research packet

It does not simply search freely on its own.  
It mainly works from the structured information already available inside the system.

### 11.2 What the AI Agent reads

It reads:

- price data
- technical indicators
- news summaries
- social sentiment
- outputs from `Detail`
- outputs from `Social`

### 11.3 What the AI Agent does

It organizes these inputs into:

- a more complete report
- a more readable final judgment

So the main value of this layer is:

- interpretation and integration

---

## 12. Team: Multi-Agent Decision Layer

The `Team` page is the part of the project that comes closest to an investment committee workflow.  
It introduces a multi-agent process for higher-level decision making.

### 12.1 Core idea of Team

Different agents analyze the same stock from different perspectives, such as:

- news and events
- sentiment and discussion activity
- technical behavior
- risk

Then a higher-level agent produces a combined conclusion.

### 12.2 Main functions of the Team page

This page shows:

- the outputs of multiple agents
- reports from different viewpoints
- a final combined decision-style judgment

### 12.3 Positioning of Team

It is not a single prediction page.  
It is a:

- multi-perspective
- multi-role
- decision-oriented layer

So it is best understood as the decision layer of the system.

---

## 13. Ops: Automation and Control Layer

The `Ops` page is responsible for showing and controlling the automation workflow.

### 13.1 Daily Update

This step mainly handles:

- updating OHLC
- updating news
- updating social sentiment
- running preprocessing and data completion tasks

### 13.2 Batch Collect

This step mainly handles:

- collecting batch results
- training models
- generating and refreshing forecasts

### 13.3 Main functions of the Ops page

The user can use `Ops` to:

- see whether a pipeline is running
- see which step it is currently on
- review recent runs
- manually trigger:
  - `Run Daily Update`
  - `Run Batch Collect`

### 13.4 Positioning of Ops

The `Ops` page is what turns the system from a static interface into a:

- updatable
- trainable
- monitorable

automated platform.

---

## 14. Relationship Between the Modules

The whole system can be understood as a layered structure:

### Data layer

- price
- news
- social sentiment

### Prediction layer

- `Detail`
- `Social`

### Visualization layer

- `Sentiment`

### Interpretation layer

- `Analysis`
- `AI Agent`

### Decision layer

- `Team`

### Operations layer

- `Ops`

In other words, the system works like this:

- data enters the platform
- the platform generates forecasts
- the LLM organizes and explains the signals
- multiple agents combine perspectives into a decision-style output
- automation keeps the whole workflow running continuously

---

## 15. Main Characteristics of the Project

IvyTrader stands out in four main ways.

### 15.1 Dual forecasting pipelines

It does not rely on only one model or one source of information.  
It keeps both:

- a news-driven perspective
- and a sentiment-driven perspective

### 15.2 Strong explainability

The platform does not only show a result.  
It also provides:

- drivers
- similar history
- key news
- AI explanations

### 15.3 Clear layered structure

Prediction, interpretation, decision making, and automation are separated into clear layers, making the system easier to extend and maintain.

### 15.4 Automation

This is not just a static demo.  
It is a system with real data updates, model training, forecast generation, and monitoring.

---

## 16. Final Summary

IvyTrader is a stock research platform built around the theme of:

- price
- news
- sentiment
- machine learning
- LLM analysis
- automation

Through:

- the news-driven `Detail` page
- the sentiment-driven `Social` page
- the visualization-focused `Sentiment` page
- the interpretation-focused `Analysis` and `AI Agent` layers
- the multi-agent `Team` decision layer
- and the automation-focused `Ops` page

it brings originally separate research workflows into one unified system.

The final goal of the project is not simply to build a model that predicts up or down.  
It is to build a platform that can:

- update data continuously
- generate forecasts
- explain its reasoning
- and support multi-perspective decision making

for every ticker in the system.
