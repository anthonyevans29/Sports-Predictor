**2026-10-09 — FINDING (ARCHITECT 2026-10-09 18:37 ET, addendum 30 item 1, logged, nothing built; Issue #399): the provider re-issued the game ids of its 2026 college schedule on 2026-10-09.** Verbatim:

> 1. FINDING: THE PROVIDER RE-ISSUED THE GAME IDS OF ITS 2026 COLLEGE SCHEDULE ON 2026-10-09. A BACKLOG entry and an
> Issue (finding, ncaa), nothing built. The receipts are the operator's console on the laptop at ed5ecbb, 22:06Z to
> 22:12Z; the long ones are in RECEIPTS A below, verbatim.
> - by date 2026-10-09: "created=0 updated=2 skipped=1 rekeyed=2 rekey_refused=0"
> - by date 2026-10-10: "created=4 updated=85 skipped=8 rekeyed=85 rekey_refused=0"
> - by date 2026-10-11: "created=0 updated=6 skipped=1 rekeyed=5 rekey_refused=1". The refusal: "api_american_football
>   id 25153 NOT created — stored row 32825 holds its natural key but its id 24199 is still in this listing (the
>   provider lists both 24199 and 25153)".
> - refresh-by-id: asked 110, unchanged 97, not found 13. The 13: matches 32740, 32764 and 32773, all stored at
>   2026-10-10 04:00; 48549, stored 2026-10-10 18:00; and 32828 to 32836, nine games of 2026-10-13 to 2026-10-16
>   whose dates no listing read has covered since the ids changed.
> - the season listing: 1756 games, 953 of them NS. At 12:27Z it held 841 and 51 (addendum 21).
> - "Football odds: created=14647 across 17 games (NCAA 3/202 · NFL 14/15 priced/in window)"
> From the laptop's fixtures file of 22:09:54Z: the four created rows are 50507 (Bryant @ Brown, 16:00Z, a game we
> did not hold) and 50508, 50509 and 50510: South Carolina @ Florida at 16:45Z, UAB @ Memphis at 23:00Z and James
> Madison @ Georgia Southern at 23:30Z, each beside its 04:00Z row (32740, 32764, 32773). The three college games
> priced are those three 04:00Z rows: 7, 7 and 8 books stamped 22:07Z, on ids the games endpoint no longer returns.
> Every re-keyed row printed "no odds yet", Georgia @ Alabama among them, which answered with 8 bookmakers on its old
> id at 12:27Z.
> What that means, from the code: sync_odds_nfl asks /odds by the row's current id only, and the capture time is our
> clock, not the provider's (list_odds). So tonight no live college row has a fresh book price, and three
> placeholder rows carry prices stamped 22:07Z that may be frozen. College is market-only and all 108 rows were
> PASS; Kalshi was on 94 of the 114 rows in the file. Nothing is built for the odds yet: the operator runs a
> read-only probe (odds by the new id and by the old one, with the provider's own update time) and I rule on it
> then.

- **Receipts (addendum 30, RECEIPTS A, verbatim):**

```
REFRESH-BY-ID NCAA (api_american_football) window 2026-10-09 00:00 .. 2026-10-17 00:00 UTC · selected 110 · asked 110 · unchanged 97 · updated 0 (kickoff moved 0, status 0, score 0) · not found 13 · refused 0 · no id 0 · unresolved 0 · rate limited 0 (recovered 0, still 0) · requests 110
  NOT FOUND by id (untouched): match 32740 id 23616 South Carolina @ Florida stored 2026-10-10 04:00
  NOT FOUND by id (untouched): match 32764 id 23618 UAB @ Memphis stored 2026-10-10 04:00
  NOT FOUND by id (untouched): match 32773 id 23619 James Madison @ Georgia Southern stored 2026-10-10 04:00
  NOT FOUND by id (untouched): match 48549 id 24170 Virginia Lynchburg @ Norfolk State stored 2026-10-10 18:00
  NOT FOUND by id (untouched): match 32828 id 23662 Delaware @ Middle Tennessee stored 2026-10-13 23:00
  NOT FOUND by id (untouched): match 32829 id 23663 Florida International @ Jacksonville State stored 2026-10-14 00:00
  NOT FOUND by id (untouched): match 32830 id 23664 Kennesaw State @ Missouri State stored 2026-10-14 23:30
  NOT FOUND by id (untouched): match 32831 id 23665 Western Kentucky @ Sam Houston stored 2026-10-15 00:00
  NOT FOUND by id (untouched): match 32832 id 23666 East Carolina @ UAB stored 2026-10-15 23:30
  NOT FOUND by id (untouched): match 32833 id 23667 Georgia Southern @ Old Dominion stored 2026-10-15 23:30
  NOT FOUND by id (untouched): match 32834 id 23668 Colorado State @ Texas State stored 2026-10-16 00:00
  NOT FOUND by id (untouched): match 32835 id 24201 Columbia @ Pennsylvania stored 2026-10-16 23:00
  NOT FOUND by id (untouched): match 32836 id 23669 Memphis @ Tulane stored 2026-10-16 23:30
REFRESH-BY-ID-RECEIPT {"asked": 110, "competition": "NCAA", "days": 7, "excluded": 0, "kickoff_moved": 0, "kind": "refresh_by_id", "no_id": 0, "not_found": 13, "now": "2026-10-09 22:06", "rate_limited": 0, "recovered": 0, "refused": 0, "requests": 110, "score_changed": 0, "selected": 110, "source": "api_american_football", "status_changed": 0, "still_rate_limited": 0, "unchanged": 97, "unresolved": 0, "updated": 0, "window": ["2026-10-09 00:00", "2026-10-17 00:00"]}
PROBE (i) NCAA SEASON LISTING at 2026-10-09T22:12Z (read-only; 1 provider call; nothing written)
  games 1756 · by status {'FT': 778, 'AOT': 23, 'CANC': 1, 'PST': 1, 'NS': 953}
  listed games kicking off after now: 946 · per day {'2026-10-09': 2, '2026-10-10': 97, '2026-10-11': 7, '2026-10-13': 1, '2026-10-14': 2, '2026-10-15': 4, '2026-10-16': 3, '2026-10-17': 107}
  OUR stored SCHEDULED NCAA games in the next 7 days: 108 · provider id in the listing: 97 · NOT in the listing: 11
```

- **The architect's correction of addendum 21 item 1, in the same entry (addendum 30 item 2, also on #377), verbatim:**

> 2. A CORRECTION OF MINE, in the same entry and as a comment on #377. Addendum 21 item 1 said "No twins" and "The
> host's placeholders are games whose time was announced after the host last read them", and your entry drew from
> it that the twin case "does not arise from these games". My two sentences were true of the files I had read. The
> host's later files say more (exports mirror, host at 0023368):
> - fixtures file of 2026-10-08T16:00:51Z: 104 scheduled rows, no pairing twice, 38 rows at 04:00Z, highest match id
>   8469.
> - fixtures file of 2026-10-09T16:00:28Z: 132 scheduled rows, 27 pairings twice. Its 30 rows at 04:00Z are all
>   Saturday's, and 27 of them stand beside a second row, ids 47641 to 47668, at a real kickoff between 16:30Z and
>   23:30Z (Georgia @ Alabama: 8376 at 04:00Z, 47665 at 23:30Z). No second row is at 16:00Z or earlier. 25 of the 27
>   second rows carry books, and every book capture on a scheduled row is between 00:06:04Z and 00:06:30Z on
>   2026-10-09. No placeholder row carries books or Kalshi.
> - window card of 2026-10-09T22:07:43Z: 108 college rows, the same 30 at 04:00Z, and no book capture newer than
>   00:06:26Z on any college row.
> So on the host the announced times arrived on second rows, and they were there by 00:06Z on 2026-10-09; the window
> run of 00:05Z was the first to read Saturday's date. From the code that is your case (b): the listing carried
> those games under ids the placeholder rows did not hold, each more than 12 hours from 04:00Z, and the 12-hour rule
> created them. Which ids the two rows of a pair hold, and whether the host's rows were re-keyed again during the
> day, the files do not say. The host's dedupe-matches --orphans dry run does, and the operator runs it.
> The ruling of addendum 21 stands as issued: the refresh is by id, and the listing reads find what we do not hold.
- **The odds question (addendum 32 items 2 and 3, 2026-10-09 19:02 ET):** the payload read (NCAA game 23616 carries response[].update, "2026-10-08T02:15:10+00:00", dropped by the adapter: match 32740's 22:07Z prices were frozen and stamped as fresh) and the ruling on what `update` is are recorded verbatim in docs/ledger/entries/2026-10-09-addendum-32-odds-payload.md.
