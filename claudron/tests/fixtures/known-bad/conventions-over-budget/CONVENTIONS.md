# Vault conventions

This CONVENTIONS file exists to blow the token budget deliberately, because
the whole point of the always-loaded conventions layer is that it stays tiny
enough to inject into every single session brief without displacing the
context the agent actually needs for its task. When a conventions file grows
past its budget it stops being a cheap standing preamble and starts being a
tax on every session, which is exactly the failure mode the W105 warning
exists to catch before it compounds. So this paragraph keeps going, adding
filler sentence after filler sentence about timezone conventions, naming
conventions, linking conventions, promotion conventions, supersession
conventions, capture conventions, review-queue conventions, and sync
conventions, until any reasonable tokenizer counts well past one hundred
sixty tokens of body content, which is the grace ceiling above the nominal
one-hundred-twenty-token budget that the schema assigns to this file.
