# BUGFIX_BRIEF

## Bug

PR #34 implements SymbolUniverse / exchangeInfo-as-truth symbol validation.

But CandidatePool still case-folds symbols:

- CandidatePool.offer():
  symbol = (snapshot.symbol or "").upper().strip()

- CandidatePool.get():
  self._candidates.get((symbol or "").upper().strip())

- CandidatePool.remove():
  self._candidates.pop((symbol or "").upper().strip(), None)

This conflicts with SymbolUniverse's exact-match canonical symbol contract.

SymbolUniverse explicitly says:
- valid_symbol_set is built from Binance exchangeInfo
- membership is exact-match on the canonical string Binance returns
- do NOT case-fold with .upper() / .lower()
- only strip surrounding whitespace

## Expected Behavior

CandidatePool must preserve the exact Binance exchangeInfo canonical symbol string.

Allowed:
- strip surrounding whitespace

Forbidden:
- .upper()
- .lower()
- ASCII-only symbol regex
- any character-class filter that rejects non-ASCII symbols

## Suspected Files

- app/market_data_public/candidate_pool.py
- tests/unit/test_phase11c_1b_symbol_universe.py

## Forbidden Files

Do not modify:
- app/risk/*
- app/execution/*
- app/llm/*
- app/telegram/*
- app/config/schema.py
- scripts/run_public_market_paper.py

## Required Code Changes

In app/market_data_public/candidate_pool.py:

1. In CandidatePool.offer():

Replace:
symbol = (snapshot.symbol or "").upper().strip()

With:
symbol = str(snapshot.symbol or "").strip()

2. In CandidatePool.get():

Replace:
return self._candidates.get((symbol or "").upper().strip())

With:
return self._candidates.get(str(symbol or "").strip())

3. In CandidatePool.remove():

Replace:
return self._candidates.pop((symbol or "").upper().strip(), None)

With:
return self._candidates.pop(str(symbol or "").strip(), None)

## Required Tests

Add or update tests:

- test_candidate_pool_does_not_uppercase_exchange_info_symbol
- test_candidate_pool_get_preserves_exchange_info_canonical_string
- test_candidate_pool_remove_preserves_exchange_info_canonical_string
- test_symbol_validation_preserves_exchange_info_canonical_string

Test requirements:
1. A non-ASCII symbol in exchangeInfo must be admitted exactly.
2. CandidatePool must not uppercase/lowercase the symbol.
3. get() and remove() must use the exact symbol string.
4. ASCII-only regex audit must still pass.

## Commands

Run targeted tests first:

```bash
python -m pytest tests/unit/test_phase11c_1b_symbol_universe.py -q
