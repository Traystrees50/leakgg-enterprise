# Handoff

## Status: Step 1 in progress

## Current Work
- Git repo initialized, `feature/event-code-detection` branch created
- `.kilo/` state files created and committed

## Next Agent Actions
1. STEP 2: Create `scrapers/ocr.py`
2. STEP 3: Create `bonus_code_detector.py`
3. STEP 4: Integrate OCR fallback into `scrapers/telegram.py`
4. STEP 5: Add tests to `test_bot.py`
5. STEP 6: Run tests, validate no regressions

## Key Context
- Three ingestion paths converge in `TelegramScraper` / `ScraperEngine.process_items`
- Placeholder code pattern: `CHECK_IMAGE_FOR_CODE_#msg_id` (triggers OCR fallback)
- No new deps allowed — OCR via OCR.space API using existing `requests`
- Target Discord embed layout already exists in `DiscordNotifier.build_embed`
- Tests run with `python test_bot.py` (currently 63/64 pass)
- Bot running online (PID 24664) — keep changes additive and non-breaking
