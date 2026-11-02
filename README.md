# When Titans Clash — Stock Monitor

A browser-based tracker for public comic listings on [When Titans Clash](https://www.whentitansclash.co.uk/).

## What it does

- Scans catalogue pages using GitHub Actions, approximately every 12 hours.
- Builds a searchable dashboard with title, grade/condition, price and direct listing link.
- Records first detection, price changes, restocks and listings that disappear from the catalogue.
- Uses detection dates only; it does not claim to know the seller's actual upload date.
- Requires two consecutive missed scans before marking an item as removed.

## One-time setup

1. In this repository, open **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions** and save.
3. Open **Actions → Scan When Titans Clash catalogue**.
4. Select **Run workflow**, then **Run workflow** again to start the first inventory scan.

The first successful scan establishes the baseline. Existing stock is recorded but is not labelled as newly listed. Later scans detect changes.

## Dashboard

Once the first workflow run has completed successfully, the dashboard will be available at:

https://desconocidas666.github.io/when-titans-clash-tracker/

## Important coverage note

The crawler follows catalogue pages linked from the SellerDeck catalogue and extracts product-like listing blocks. The first run must be checked for successful completion and a plausible page/listing count before treating coverage as exhaustive. The public site may change its page structure, so selectors may need adjustment.

The monitor is deliberately polite (small delay between page requests). GitHub's scheduled workflow timing is approximate and may be delayed by GitHub.
