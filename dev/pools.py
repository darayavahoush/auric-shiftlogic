import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Phrasing pools. VIS = decoys seen in items.json. NEW = wording NOT in items.json (held-out style)."""
from templates import VISIBLE

# ---------- NEW binding templates (disjoint from items.json wording) ----------
NEW = [
 ("BLOCK_EQ","{A} has been given the {T} slot.",("A","T")),
 ("BLOCK_EQ","{A} will be working {T}.",("A","T")),
 ("BLOCK_EQ","The {T} slot belongs to {A}.",("A","T")),
 ("BLOCK_EQ","{A} is rostered on at {T}.",("A","T")),
 ("BLOCK_NEQ","{A} can't do the {T} slot.",("A","T")),
 ("BLOCK_NEQ","{A} isn't working {T}.",("A","T")),
 ("BLOCK_NEQ","The {T} slot isn't one {A} has.",("A","T")),
 ("BLOCK_NEQ","{A} will not be in at {T}.",("A","T")),
 ("STATION_EQ","{A} has been posted to {S}.",("A","S")),
 ("STATION_EQ","{A} will cover {S}.",("A","S")),
 ("STATION_EQ","{A} is the {S} person.",("A","S")),
 ("STATION_EQ","{S} goes to {A}.",("A","S")),
 ("STATION_EQ","{A} is stationed at {S}.",("A","S")),
 ("STATION_NEQ","{A} won't be covering {S}.",("A","S")),
 ("STATION_NEQ","{A} isn't the {S} person.",("A","S")),
 ("STATION_NEQ","{S} does not go to {A}.",("A","S")),
 ("STATION_NEQ","{A} is not stationed at {S}.",("A","S")),
 ("ORDER_LT","{A} goes on ahead of {B}.",("A","B")),
 ("ORDER_LT","{A} is finished before {B} begins.",("A","B")),
 ("ORDER_LT","{B} is not on until after {A}.",("A","B")),
 ("ORDER_LT","{A}'s shift comes earlier in the day than {B}'s.",("A","B")),
 ("ORDER_LT","{A} is in an earlier block than {B}.",("A","B")),
 ("ORDER_GT","{A} goes on after {B}.",("A","B")),
 ("ORDER_GT","{A} does not start until {B} has finished.",("A","B")),
 ("ORDER_GT","{A} is in a later block than {B}.",("A","B")),
 ("ORDER_GT","{B} is already done by the time {A} comes on.",("A","B")),
 ("IMMEDIATE_AFTER","{A} follows straight on from {B}.",("A","B")),
 ("IMMEDIATE_AFTER","{A} takes the block right after {B}.",("A","B")),
 ("IMMEDIATE_AFTER","{A} is the very next person on after {B}.",("A","B")),
 ("IMMEDIATE_AFTER","{B} is immediately followed by {A}.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} is immediately followed by {B}.",("A","B")),
 ("IMMEDIATE_BEFORE","{B} comes on right after {A}.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} hands over to {B} with nothing in between.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} is the one directly ahead of {B}.",("A","B")),
 ("BETWEEN","{M} is wedged between {A} and {B}.",("M","A","B")),
 ("BETWEEN","{A} and {B} bracket {M}, in either order.",("M","A","B")),
 ("BETWEEN","{M} is the middle one, time-wise, of {A}, {M} and {B}.",("M","A","B")),
 ("BETWEEN","In the running order, {M} lands somewhere between {A} and {B}.",("M","A","B")),
 ("BETWEEN","{M} comes after {A} but before {B}, or the other way round.",("M","A","B")),
 ("ORDER_STATION_PERSON","Whoever covers {S} goes on ahead of {A}.",("S","A")),
 ("ORDER_STATION_PERSON","The {S} person finishes before {A} comes on.",("S","A")),
 ("ORDER_STATION_PERSON","{S} is staffed ahead of {A}'s block.",("S","A")),
 ("ORDER_PERSON_STATION","{A} starts after whoever is working {S}.",("A","S")),
 ("ORDER_PERSON_STATION","{A} is later in the day than the {S} person.",("A","S")),
 ("ORDER_PERSON_STATION","{A} comes on once the {S} person has finished.",("A","S")),
]
NEW_HEDGES = ["From what I recall, ","I believe ","If memory serves, ","Unless I have this wrong, ","I'm reasonably confident "]
NEW_WRAPPERS = ["Worth flagging again: ","Second mention: ","Repeating for the record: ","To say it once more: "]

# ---------- decoys: placeholders {A} {B} {T} {S} {L}(name list) ----------
NEW_DECOY = {
 "CHAT": [
  "The label printer was swapped out on Tuesday.","Someone keeps leaving the loading bay door ajar.",
  "The vending machine near reception is out of order again.","{A} borrowed the pallet jack last week.",
  "{A} is bringing cake in on Friday.","The briefing room has a new whiteboard.",
  "{L} all signed the card for the retiring supervisor.","Safety gloves are now stocked on the second shelf.",
  "{A} parked in the wrong bay again.","The forklift charging schedule was reprinted.",
  "{L} took part in the first-aid drill.","The kettle in the break room has been descaled.",
 ],
 "PAST": [
  "Two cycles ago, {A} ran {S}.","Before the reshuffle, {A} had the {T} block.",
  "Historically {S} used to be {A}'s.","Last quarter {A} was on {S} most weeks.",
 ],
 "WISH": [
  "If {A} were on {T}, the handover would be cleaner.","It would have been neater to put {A} on {S}.",
  "{A} would be a natural fit for {S}, in theory.","Had {A} been free, {A} would have taken {T}.",
 ],
 "OPEN": [
  "It is still undecided whether {A} covers {S}.","Nobody has confirmed whether {A} is in at {T}.",
  "Whether {A} gets {S} was never settled.","Someone should check whether {A} is on {T}.",
 ],
 "UNMET": [
  "{A} asked for {T} and was told no.","{A} had requested {S}, but that was not approved.",
  "{A}'s bid for the {T} slot was rejected.","{A} tried to swap into {T} but nothing came of it.",
 ],
}
VIS_DECOY = {
 "CHAT": [
  "The visitor log was moved to the front desk in March.","Nobody has claimed the jacket left in the break room.",
  "The recycling collection has moved to Wednesdays.","Catering is unchanged from last week.",
  "The site coordinator noted that the car park resurfacing runs through the end of the month.",
  "{A} filled in the equipment survey.","{A} and {B} car-share when their shifts allow.","Deliveries continue to arrive through the north gate.",
  "{A} has the spare key to the supply cupboard.","{A} left a note about the recycling bins.","{A} has been chasing the maintenance ticket for the printer.",
  "{A} appeared on the old emergency contact sheet.","{A} joined the site walkaround in March.","{A} completed the fire-safety refresher last quarter.",
  "{L} completed the fire-safety refresher last quarter.","{A} keeps the sign-in sheet in the top drawer.","{A} sat on the interview panel in February.",
  "{L} attended the supplier training day in the spring.","{A} is the point of contact for the fire drill.",
 ],
 "PAST": ["In the spring {A} held {S} for a while.","Back in the old arrangement, {A} took {S}.","Last month {A} was on {S}.","On the previous cycle {S} was {A}'s."],
 "WISH": ["If {A} had taken the {T} block the handover would have been smoother.","{A} would have been a better fit for the {T} block.",
          "Had the rota gone the other way, {A} would be on {T}.","Putting {A} on the {T} block would have solved the parking problem."],
 "OPEN": ["There was some disagreement about whether {A} had {T}.","Nobody could remember whether {A} was down for the {T} block.",
          "The question of {A} on {T} was left open in the handover.","{A} and the {T} block came up, but nothing was minuted."],
 "UNMET": ["{A} lobbied for {T} without success.","{A} put in for the {T} block and was turned down.",
           "{A} wanted {T} and did not get it.","{A} asked to move to the {T} block; the request was declined."],
}
VIS_HEDGES = ["As far as I know, ","Speaking from memory, ","My recollection is that ","I'm fairly sure ","Going off the roster, "]
VIS_WRAPPERS = ["It bears repeating: ","Noted twice in the handover: ","This came up more than once, so: ","Worth restating, since it came up twice in handover: "]
POOLS = {
 "new": dict(bind=NEW, decoy=NEW_DECOY, hedges=NEW_HEDGES, wrappers=NEW_WRAPPERS),
 "visible": dict(bind=VISIBLE, decoy=VIS_DECOY, hedges=VIS_HEDGES, wrappers=VIS_WRAPPERS),
}

# Decisive phrase per NEW template, used only by the eval to split lines into "phrase is in the prompt glossary" vs not.
# "STATION person" = the "<station> person" construction.
PHRASE = {
 "{A} has been given the {T} slot.": "given the", "{A} will be working {T}.": "will be working",
 "The {T} slot belongs to {A}.": "belongs to", "{A} is rostered on at {T}.": "rostered on",
 "{A} can't do the {T} slot.": "can't do", "{A} isn't working {T}.": "isn't working",
 "The {T} slot isn't one {A} has.": "isn't one", "{A} will not be in at {T}.": "will not be in",
 "{A} has been posted to {S}.": "posted to", "{A} will cover {S}.": "will cover",
 "{A} is the {S} person.": "STATION person", "{S} goes to {A}.": "goes to", "{A} is stationed at {S}.": "stationed at",
 "{A} won't be covering {S}.": "won't be covering", "{A} isn't the {S} person.": "STATION person",
 "{S} does not go to {A}.": "does not go to", "{A} is not stationed at {S}.": "stationed at",
 "{A} goes on ahead of {B}.": "ahead of", "{A} is finished before {B} begins.": "finished before",
 "{B} is not on until after {A}.": "not on until after", "{A}'s shift comes earlier in the day than {B}'s.": "earlier in the day than",
 "{A} is in an earlier block than {B}.": "earlier block",
 "{A} goes on after {B}.": "goes on after", "{A} does not start until {B} has finished.": "does not start until",
 "{A} is in a later block than {B}.": "later block", "{B} is already done by the time {A} comes on.": "by the time",
 "{A} follows straight on from {B}.": "straight on from", "{A} takes the block right after {B}.": "right after",
 "{A} is the very next person on after {B}.": "very next", "{B} is immediately followed by {A}.": "immediately followed by",
 "{A} is immediately followed by {B}.": "immediately followed by", "{B} comes on right after {A}.": "right after",
 "{A} hands over to {B} with nothing in between.": "nothing in between", "{A} is the one directly ahead of {B}.": "directly ahead of",
 "{M} is wedged between {A} and {B}.": "wedged between", "{A} and {B} bracket {M}, in either order.": "bracket",
 "{M} is the middle one, time-wise, of {A}, {M} and {B}.": "middle one",
 "In the running order, {M} lands somewhere between {A} and {B}.": "lands somewhere between",
 "{M} comes after {A} but before {B}, or the other way round.": "or the other way round",
 "Whoever covers {S} goes on ahead of {A}.": "ahead of", "The {S} person finishes before {A} comes on.": "STATION person",
 "{S} is staffed ahead of {A}'s block.": "staffed ahead of",
 "{A} starts after whoever is working {S}.": "starts after whoever", "{A} is later in the day than the {S} person.": "later in the day than",
 "{A} comes on once the {S} person has finished.": "comes on once",
 "Two cycles ago, {A} ran {S}.": "two cycles ago", "Before the reshuffle, {A} had the {T} block.": "before the reshuffle",
 "Historically {S} used to be {A}'s.": "historically", "Last quarter {A} was on {S} most weeks.": "last quarter",
 "If {A} were on {T}, the handover would be cleaner.": "were on", "It would have been neater to put {A} on {S}.": "neater",
 "{A} would be a natural fit for {S}, in theory.": "natural fit", "Had {A} been free, {A} would have taken {T}.": "would have taken",
 "It is still undecided whether {A} covers {S}.": "still undecided", "Nobody has confirmed whether {A} is in at {T}.": "has confirmed",
 "Whether {A} gets {S} was never settled.": "never settled", "Someone should check whether {A} is on {T}.": "should check",
 "{A} asked for {T} and was told no.": "told no", "{A} had requested {S}, but that was not approved.": "not approved",
 "{A}'s bid for the {T} slot was rejected.": "rejected", "{A} tried to swap into {T} but nothing came of it.": "nothing came of it",
}
