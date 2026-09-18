# v0.17.7

App version: **0.17.7**  
Build: **30**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Connection watchdog correction

The v0.17 reliability pass introduced a 12-second timeout for Hades II `connect`. Historical successful target-Mac logs show LLDB attach + symbol validation + first Lua bootstrap can legitimately take more than 50 seconds. The watchdog therefore terminated healthy connections before they completed.

Timeout policy is now:

- scan: 15 s
- status: 8 s
- connect: 90 s
- disconnect: 12 s

This is intentionally a Hades-local policy; Core request timeout enforcement remains unchanged.

## Why the UI looked unchanged/green

v0.17.5–0.17.6 primarily moved the existing visual components into Core without redesigning them, so a visual diff was expected to be small. The green feature switches shown while testing are the pre-existing **detached/deferred desired-state** color. They indicate the feature is remembered as enabled while there is no confirmed live runtime connection. The failed 12-second attach made that state persist.

The lower boon controls use native compact switches in the pre-decoupling baseline as well, so they intentionally remain visually different from the 44×25 feature switches.
