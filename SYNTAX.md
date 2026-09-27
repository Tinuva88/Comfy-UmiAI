# Umi Prompt Syntax

This is the compact syntax reference for the `UmiAI Wildcard Processor`. For
installation, node descriptions, and workflow guidance, see `README.md`.

## Wildcards

Pick one line from a file in `wildcards/`:

```text
__pose__
```

Use a fallback if the wildcard is missing:

```text
__pose|standing confidently__
```

Pick multiple values:

```text
__1-3$$accessories__
```

Use a sequential stream:

```text
__~pose__
```

Sequential picks line `seed % line_count` from the file. It advances only when
the node seed changes (set the seed widget to *increment* to cycle through the
file in order). `__~2-3$$pose__` takes a contiguous run of lines starting at
that index, wrapping at the end of the file.

### Repeating a wildcard

Writing the same wildcard twice in the body of a prompt reuses the first
resolved value, so the two agree:

```text
__color__ shirt, __color__ pants
```

That produces a matching pair. Assigning the same wildcard to *different*
variables is treated as a different request, and each one rolls separately:

```text
$top={__color__}
$skirt={__color__}
```

`$top` and `$skirt` get different colours. Values are drawn without
replacement, so sibling variables differ wherever the file has enough lines to
go around; once the pool is exhausted it starts reusing values rather than
failing. A file with two lines asked for three variables therefore yields two
distinct values and one repeat.

Assigning once and reusing the variable keeps a single value, as you would
expect:

```text
$c={__color__}, $c shirt, $c pants
```

To roll the same file independently *without* variables, give each occurrence
its own scope with `@name:`:

```text
__@a:color__ and __@b:color__
```

Scopes follow the same distinctness rule as variables. Unscoped occurrences are
unaffected and still share one value among themselves.

Insert a whole prompt file:

```text
__@scene_intro__
```

Use YAML or file tag logic:

```text
__[soft AND light]__
__lighting[dramatic OR backlit]__
```

Boolean logic supports `AND`, `OR`, `NOT`, `XOR`, and parentheses.

## YAML Wildcards

A `.yaml` file in `wildcards/` holds named entries rather than one candidate
per line. An entry carries the tags it can be found by, the prompts it can
resolve to, and optional text to inject around the prompt:

```yaml
Soft Glow:
  Tags: [soft, light, mood]
  Prompts: [gentle glow, warm haze]
  Prefix: [masterpiece]
  Suffix: [bokeh]
  Neg_Prefix: [harsh lighting]
  Neg_Suffix: [flat]
  Description: [a soft, hazy look]
```

Only `Prompts` is required. `Tags` is what makes an entry findable by tag
logic; without it the entry can still be selected by name.

Every field takes a single value or a list, and every item of a list is used:

```yaml
Plain Entry:
  Tags: portrait
  Prompts: a quiet portrait
  Prefix: [masterpiece, best quality]
```

Field names are matched without regard to case, so `Tags:` and `tags:` both
work. The spellings above are the documented ones.

### Selecting an entry

```text
<[Soft Glow]>                  the entry with that name
<[soft]>                       any entry tagged soft
<[soft AND light]>             tag logic, same operators as above
__[hard OR dark]__             the same thing in wildcard form
__style[soft]__                only entries in style.yaml
```

An expression is treated as an entry name first and as tag logic otherwise.
When nothing matches, the prompt shows `[NO_MATCHES: ...]` rather than failing
silently, and an entry with no `Prompts` shows `[NO_PROMPTS: ...]`.

Prompts inside an entry are ordinary prompt text, so wildcards, choices, and
variables all work in them:

```yaml
Nested Entry:
  Tags: [nested]
  Prompts: [a __color__ coat, a {red|blue} coat]
```

A YAML file that does not parse is skipped with an error on the console, and
the rest of the collection is unaffected. The Wildcards panel shows the parse
error against the file and refuses to save one that would not load.

## Inline Choices

Pick one option inline:

```text
{red dress|blue dress|black armor}
```

Each occurrence rolls on its own, so ten `{0|1|2|3|4}` in one prompt give ten
independent digits. To make two places agree, assign once and reuse the
variable:

```text
$c={red|blue}, $c shirt, $c pants
```

A value that must contain a comma needs braces or quotes, because an
undelimited assignment ends at the first comma:

```text
$mood=happy, portrait          # $mood is "happy"
$desc='a, b, c', $desc         # $desc is "a, b, c"
```

## Variables

Store and reuse values:

```text
$hair={red|blue|silver}, $hair hair, portrait
```

Variable display methods can format a reused value without changing what was
stored. `$name.clean` replaces underscores and hyphens with spaces, while
`$name.anima` follows Anima's tag convention by replacing underscores only and
preserving meaningful hyphens:

```text
$pose=back-to-back, $pose.anima
$character=fern_(sousou_no_frieren), $character.anima
```

Variables can be reused in conditionals:

```text
$mood=happy, [if $mood==happy: smiling | neutral expression]
```

### Scoped Variables

`$@name` is a variable too. It is written and read the same way, and like
`$name` it is resolved once, so every use agrees:

```text
$@mood={soft|sharp}, $@mood light, $@mood shadow
```

The difference is that a `$@` assignment made inside a conditional branch stays
in that branch. A branch that is not taken cannot define anything:

```text
[if $time==night: $@key=moonlight; $@key rim light else: daylight]
```

Undelimited values end at the first comma, exactly as `$name=` does. Use braces
or quotes for a value that must contain one.

### Global Variables

`globals.yaml` in any wildcard folder defines variables available to every
prompt. Keys may be written with or without the `$` prefix; both resolve as
`$name` in prompts and conditionals:

```yaml
$hair: silver
mood: calm
```

Inline assignments (`$hair=...` in the prompt) override globals for that run.
When the same name exists in several wildcard folders, the last folder
searched wins.

## Conditionals

Use `if`, `elif`, and `else` branches:

```text
[if $weather==rain: wet hair elif $weather==snow: winter coat else: sunny day]
```

## Negative Prompts

Inline negative tags are collected into the negative output:

```text
portrait [neg: blurry, bad hands]
```

Bold negative shorthand:

```text
portrait **watermark** **text**
```

CLI-style negative text:

```text
portrait --neg: "blurry, bad hands"
```

Block negative text:

```text
[negative]
worst quality, low quality, bad anatomy
[/negative]
```

Conditional negative text:

```text
[neg_if:$style==photo]cartoon shading[/neg_if]
```

## Prompt Functions

Clean comma spacing:

```text
[clean: masterpiece,, best quality,  detailed]
```

Shuffle comma-separated items:

```text
[shuffle: red, blue, green]
```

Choose one option:

```text
[choose: red|blue|green]
```

Sample a fixed or ranged count:

```text
[sample 2-3 from: hat|gloves|boots|scarf]
```

Function items are split on top-level `|` only. Pipes inside nested `{...}`
or `[...]` stay with their item, so `[choose: {red|blue} hair | green hair]`
picks between two items, not three.

### Boolean Prompt Functions

Compose prompt fragments explicitly:

```text
[and: {red|blue} hair | glowing eyes]
[or: freckles | soft blush | wind-swept hair]
[xor: casual outfit:3 | formal outfit:1]
```

- `[and: ...]` emits every item, in source order, deterministically.
- `[or: ...]` emits a seeded non-empty subset: a count is chosen uniformly
  from 1 to the item count, that many items are sampled, and the selected
  items are emitted in source order. The same seed always picks the same
  subset.
- `[xor: ...]` emits exactly one item and supports the same `item:weight`
  syntax as `[choose:]`.

Items may contain any other Umi syntax, including nested braces, wildcards,
and other functions. An empty body resolves to nothing.

These are prompt functions that compose fragments. They are not the same as
the boolean operators inside wildcard filters, such as
`__outfit[(casual OR formal) AND NOT winter]__`, which select entries from a
wildcard file. Free-text AND/OR/XOR in normal prompt text is never
reinterpreted.

Insert a prompt preset:

```text
[preset:studio lighting]
```

Use only the negative side of a preset:

```text
[preset:anima clean negative | include=negative]
```

Use both prompt and negative preset text:

```text
[preset:anima clean lineart | include=both]
```

Use Anima helpers inline:

```text
[anima:1girl, solo, blue hair | style=clean lineart]
[anima_order:solo, 1girl, blue hair | prefix=true]
[anima_natural:portrait of a knight in a moonlit garden]
[anima_lint:1girl, solo | negative=worst quality]
```

Validation helpers:

```text
[require:$character | character]
[assert:$mode==portrait | expected portrait mode]
[forbid:$rating==safe | explicit, nude]
[prefer:$scene==night | moonlight, rim light]
```

`warn` emits text only when `$trace` or `$debug` is true:

```text
$debug=true, [warn:$scene==night | night-scene prompt active]
```

## LoRAs

Load a LoRA through the Umi node:

```text
<lora:style_model.safetensors:0.8>
```

Disable trigger-word injection for one LoRA:

```text
<lora:style_model.safetensors:0.8 trigger=off>
```

LoRA aliases can be declared in `wildcards/aliases.yaml`:

```yaml
loras:
  hero: real_hero.safetensors
```

Then used as:

```text
<lora:hero:0.8>
```

Angle brackets are what actually loads a LoRA. There is also a bracket helper
that only expands an alias into the angle-bracket form:

```text
[lora:hero:0.8]
```

That resolves to `<lora:real_hero.safetensors:0.8>` and is then loaded by the
normal pass. It does not load anything by itself, so prefer angle brackets
unless you specifically want alias expansion inside another construct.

## Presets

Prompt presets live in `prompt_presets.yaml`. They can be selected directly on
the node or inserted inline with `[preset:name]`.

## Profiles

Prompt profiles live in `prompt_profiles.yaml` and can be selected directly on
the node. Profiles can add model-family defaults and warnings for short or
mismatched prompts.

## Sections

Sections can be reordered with the node's `section_order` input:

```text
[section:quality] masterpiece, best quality
[section:character] 1girl, silver hair
[section:scene] moonlit garden
```

Set `section_order` to:

```text
quality, character, scene
```

## Settings

Width and height can be embedded in prompt text:

```text
portrait @@width=832,height=1216@@
```

Both are held to the same 64-8192 range as the node's width and height widgets.
A larger value is clamped rather than passed on, because an out-of-range size
reaches the sampler as an allocation failure rather than a slow generation.

## Cohesive Anima wildcard composition

The Wildcard Processor can compose resolved wildcard values after normal
expansion:

- `anima_prompt_mode = off`: preserve the normal expanded prompt.
- `anima_prompt_mode = ordered tags`: group Anima meta, subject, action,
  setting, composition, lighting, and style fragments.
- `anima_prompt_mode = cohesive prompt`: write those groups as deterministic
  visual sentences.
- `anima_artist_mode = split for artist mixer`: remove resolved `@artist`
  fragments from the base prompt and return them through `artist_chain`.

Example source:

```text
__AnimaFavoriteSeries_Natural__,
__alex-poses-anima-hybrid__,
__backgrounds_patterns__,
__alex-camera-framing-anima__,
__alex-lighting-anima-hybrid__,
__AnimaStyle__,
__AnimaArtists__
```

There is no fixed wildcard count. Wildcard filenames are used as semantic hints,
while unknown fragments safely fall back to subject/detail content. LoRA and
settings syntax are preserved for their later processing phases.

## Comments

In prompt text and wildcard `.txt` files:

- `//` toggles comment mode until the next `//` or end of line.
- A line starting with `#` is a comment.
- A space followed by `#` starts an inline comment (`alpha # note` keeps
  `alpha`). A `#` without a preceding space is kept (`deep#blue` stays intact).

## Processing Order

The Wildcard Processor evaluates a prompt in this order:

1. Inline `[preset:...]` and the node's preset widget.
2. `[section:name]` reordering via `section_order`.
3. Comment stripping.
4. Expansion loop (repeats until stable, default maximum 50 passes):
   `__@file__` includes -> variable assignments -> variable substitution ->
   wildcards and `<[...]>` and bracket functions -> `{a|b}` choices ->
   `[if ...]` conditionals.
5. YAML prefix/suffix injection, negative extraction, cleanup.
6. `input_negative` expansion, then the prompt profile.
7. Optional Anima tag ordering/cohesion and artist-chain splitting.
8. Bypass phrase matching, then `<lora:...>` extraction/loading.
9. `@@width/height@@` settings extraction and final cleanup.

If the loop is stopped by the iteration cap or a cycle, a warning is added to
the `explain_json` output. A warning is also added when expansion finishes with
`__name__` still in the text: a wildcard file that refers to itself never
changes the prompt, so the loop ends normally and nothing else would flag it.

UMI Settings → Processing offers optional **Preserve Newlines**, **Max Expansion
Iterations** (1–200; default 50), and **Max Expanded Prompt Chars**
(1,000–10,000,000; default 1,000,000). Newline preservation is off by default;
when enabled, final cleanup operates within each line instead of flattening
the prompt. Syntax operations, comments and model-specific profiles can still
transform their own text. The size limit is checked between expansion passes;
it is not a strict allocation budget inside each parser operation.

Missing, empty and unreadable wildcard diagnostics are included in explanation
and preview warnings. Incoming negative-prompt warnings are labeled separately.
The legacy error markers in generated text remain compatible.

Autocomplete now discovers the same TXT/YAML/YML/CSV files and search roots as
execution. `__@...__` suggestions remain TXT-only. The Wildcards browser shows
source folders and duplicate sources; external collections and CSV files are
read-only previews. Edit external files in their source folders, then Refresh.

## Keeping this reference honest

Three lists of function names have to agree: the dispatcher in
`shared_utils.py`, the `FUNCTION_NAMES` array in `js/syntax_highlight.js`, and
this document. A name present in the dispatcher but missing from the
highlighter reads to users as unsupported syntax, which is how eleven working
functions came to look broken.

`tests/js/test_syntax_highlight.mjs` asserts that every dispatcher function is
highlighted, so that half is enforced. `[section:name]` is highlighted but is
not a dispatcher function — it is handled earlier in the pipeline, during
section reordering.

## Linting

Use `Umi Prompt Syntax Lint` to check a prompt without expanding randomness. It
reports unclosed delimiters, suspicious joins, invalid wildcard ranges, unusual
LoRA options, profile warnings, and syntax counts.

## Danbooru Browser

Open the Danbooru Browser from the UmiAI sidebar to search posts by tag. Select
tags from a post, then save them as a wildcard line, append them to an existing
wildcard, edit a wildcard text file, copy them, or inject them into the selected
Umi wildcard node prompt.
