"""Built-in words, puzzles and prompts for the party games (game.py). Add your own any time."""

# ---- Wordle challenge: the secret words (common five-letter words) ----
WORDLE = """
about above actor acute admit adopt adult after again agent agree ahead alarm album alert alike alive allow alone
along alter among angel anger angle angry apart apple apply arena argue arise armor array arrow aside asset audio
avoid award aware awful bacon badge baker basic basin beach beard beast begin being belly bench berry birth black
blade blame blank blast blaze blend bless blind block blood bloom board boast bonus boost booth brain brake brand
brave bread break brick bride brief bring broad brown brush buddy build bunch burst buyer cabin cable camel candy
canoe cargo carry catch cause chain chair chalk champ chaos charm chart chase cheap check cheek cheer chess chest
chief child chili chill choir chunk civic claim clash class clean clear clerk click cliff climb clock close cloth
cloud clown coach coast cocoa coral couch count court cover crack craft crane crash crazy cream crest crime crisp
crowd crown crumb crush curve cycle daily dairy dance dealt death debut delay depth diary dirty disco dizzy dodge
donut doubt dough draft drain drama dream dress dried drift drill drink drive drown eager eagle early earth eight
elbow elder elect empty enjoy enter entry equal error essay event every exact exist extra fable faint fairy faith
false fancy feast fence ferry fever fiber field fifty fight final flame flash fleet flock flood floor flour fluid
flute focus foggy force forge forth forty forum found frame fresh fried front frost fruit fudge funny gamer ghost
giant given glass globe glove goose grace grade grain grand grape graph grass grave gravy great greed green greet
grill grind group grove guard guess guest guide habit happy harsh heart heavy hedge hello hippo hobby honey honor
horse hotel house human humor hurry igloo image index input irony issue ivory jeans jelly jewel joint jolly judge
juice jumbo jumpy kayak knife knock koala label lunar laser later laugh layer learn lemon level light limit linen
liver llama lodge logic loose lucky lunch magic major mango maple march match maybe mayor medal melon mercy merry
metal meter midst mimic minor model money month moose motel motor mount mouse mouth movie muddy music naval nerve
never night ninja noble noise north novel nurse ocean offer often olive onion opera orbit order organ other otter
ounce outer owner paint panda panel panic paper party pasta patch peace peach pearl pedal penny perch phone photo
piano piece pilot pinch pitch pizza place plain plane plant plate plaza point polar porch pound power press price
pride prime print prize proof proud puppy purse quack queen quest quick quiet quilt quite quote radar radio raise
rally ranch range rapid raven reach react ready realm relax relay reply rhyme rider ridge rifle right rival river
roast robin robot rocky rodeo rough round route royal rugby ruler rumor saint salad salsa sandy sauce scale scare
scarf scene scent scoop score scout scrap screw sense serve seven shade shake shape share shark sharp sheep shelf
shell shift shine shirt shock shore short shout siren skate skill skirt skull slate sleep slice slide slope smart
smell smile smoke snack snake sneak solar solid solve sound south space spare spark speak speed spell spend spice
spike spill spine spoon sport spray squad stack staff stage stain stair stake stamp stand start state steak steam
steel stick still stone stool store storm story stove straw strip stuck study stuff style sugar suite sunny super
swamp sweat sweet swift swing sword table taste teach teeth thank theme thick thief thing think third throw thumb
tiger tight timer toast today token topic torch total touch tough towel tower toxic track trade trail train trash
treat trend trial tribe trick truck truly trunk trust truth tulip tumor twice twist uncle under unity until upper
upset urban usual valid value vapor video vigor vinyl viral virus visit vital vivid vocal voice wagon waist waste
watch water weird whale wheat wheel where while whirl white whole width witch woman world worry worth wound woven
wrist write wrong yacht yield young youth zebra
""".split()

# ---- Drawing game: things that are fun to draw ----
DRAW = """
airplane alligator anchor angel apple astronaut backpack balloon banana bandage baseball basketball bat bathtub
beach bear bed bee bicycle bird birthday cake blender boat bone book boot bowling bridge broom bubble bucket
bunny burger bus butterfly cactus camera campfire candle car carrot castle cat caterpillar chair cheese chicken
chimney clock cloud clown coffee comb computer cookie corn couch cow crab crayon crown cupcake dinosaur dog dolphin
donut dragon drum duck eagle ear earth egg elephant envelope eyeglasses fence firetruck fish flamingo flashlight
flower football fork frog ghost giraffe glove goldfish grapes guitar hamburger hammer hat headphones heart
helicopter hippo hot dog house ice cream igloo island jellyfish kangaroo key kite knight ladder lamp leaf lemon
lighthouse lightning lion lipstick lobster lollipop magnet mailbox map mermaid microphone monkey moon mountain
mouse mushroom octopus owl paintbrush palm tree panda parachute parrot peanut pencil penguin piano pig pineapple
pirate pizza popcorn present pumpkin rainbow robot rocket roller coaster sandwich saxophone scarecrow scissors
shark sheep shoe skateboard skeleton snail snake snowman socks spaceship spider spoon squirrel star starfish
sun sunglasses surfboard swing sword taco teapot telephone tent tiger toaster toilet tooth toothbrush tornado
tractor train trampoline treasure tree trophy truck turtle umbrella unicorn vampire volcano waffle watermelon
whale wheelchair windmill witch wizard worm zebra
""".split("\n")
DRAW = [w.strip() for line in DRAW for w in line.split(" ") if w.strip()]
DRAW = [w for w in DRAW if w not in ("tree", "dog", "cream", "coaster")] + ["palm tree", "hot dog", "ice cream", "roller coaster"]
DRAW = sorted(set(w for w in DRAW if w not in ("palm", "hot", "ice", "roller")))

# ---- Wheel puzzle game: category, phrase ----
WHEEL = [
    ("Phrase", "BETTER LATE THAN NEVER"), ("Phrase", "BREAK A LEG"), ("Phrase", "PIECE OF CAKE"),
    ("Phrase", "ONCE IN A BLUE MOON"), ("Phrase", "HIT THE NAIL ON THE HEAD"), ("Phrase", "THE BALL IS IN YOUR COURT"),
    ("Phrase", "SPILL THE BEANS"), ("Phrase", "UNDER THE WEATHER"), ("Phrase", "COST AN ARM AND A LEG"),
    ("Phrase", "BURNING THE MIDNIGHT OIL"), ("Phrase", "THE EARLY BIRD CATCHES THE WORM"), ("Phrase", "NO PAIN NO GAIN"),
    ("Phrase", "LET THE CAT OUT OF THE BAG"), ("Phrase", "HOLD YOUR HORSES"), ("Phrase", "BACK TO SQUARE ONE"),
    ("Phrase", "WHEN PIGS FLY"), ("Phrase", "ACTIONS SPEAK LOUDER THAN WORDS"), ("Phrase", "EASY COME EASY GO"),
    ("Food & Drink", "PEANUT BUTTER AND JELLY"), ("Food & Drink", "CHOCOLATE CHIP COOKIES"), ("Food & Drink", "PEPPERONI PIZZA"),
    ("Food & Drink", "MACARONI AND CHEESE"), ("Food & Drink", "STRAWBERRY MILKSHAKE"), ("Food & Drink", "BUFFALO CHICKEN WINGS"),
    ("Food & Drink", "BLUEBERRY PANCAKES"), ("Food & Drink", "GRILLED CHEESE SANDWICH"), ("Food & Drink", "CHICKEN NOODLE SOUP"),
    ("Food & Drink", "HOT FUDGE SUNDAE"), ("Food & Drink", "FRENCH FRIES WITH KETCHUP"),
    ("Place", "THE GRAND CANYON"), ("Place", "NIAGARA FALLS"), ("Place", "THE EIFFEL TOWER"), ("Place", "TIMES SQUARE"),
    ("Place", "THE GOLDEN GATE BRIDGE"), ("Place", "MOUNT RUSHMORE"), ("Place", "YELLOWSTONE NATIONAL PARK"),
    ("Place", "THE STATUE OF LIBERTY"), ("Place", "THE GREAT WALL OF CHINA"), ("Place", "LAS VEGAS STRIP"),
    ("Thing", "REMOTE CONTROL"), ("Thing", "ROLLER COASTER"), ("Thing", "VIDEO GAME CONSOLE"), ("Thing", "BIRTHDAY CANDLES"),
    ("Thing", "SLEEPING BAG"), ("Thing", "SKATEBOARD RAMP"), ("Thing", "TELEVISION ANTENNA"), ("Thing", "LAVA LAMP"),
    ("Thing", "BUBBLE GUM MACHINE"), ("Thing", "WALKIE TALKIE"), ("Thing", "DISCO BALL"), ("Thing", "TREASURE CHEST"),
    ("Event", "SURPRISE BIRTHDAY PARTY"), ("Event", "FOURTH OF JULY FIREWORKS"), ("Event", "SUPER BOWL SUNDAY"),
    ("Event", "COUNTY FAIR"), ("Event", "FAMILY REUNION"), ("Event", "HALLOWEEN COSTUME CONTEST"), ("Event", "SLUMBER PARTY"),
    ("Activity", "BUILDING A SNOWMAN"), ("Activity", "PLAYING VIDEO GAMES"), ("Activity", "ROASTING MARSHMALLOWS"),
    ("Activity", "CHANNEL SURFING"), ("Activity", "WATCHING SATURDAY MORNING CARTOONS"), ("Activity", "MAKING A SANDCASTLE"),
    ("Activity", "RIDING A BICYCLE"), ("Activity", "BOWLING WITH FRIENDS"), ("Activity", "SINGING KARAOKE"),
    ("Before & After", "PEANUT BUTTER CUP OF COFFEE"), ("Before & After", "HOT DOG HOUSE PARTY"),
    ("Before & After", "BIRTHDAY CAKE WALK"), ("Before & After", "BASEBALL CAP AND GOWN"),
]

# ---- Bluff game: a true fact with a blank, and the real answer ----
BLUFF = [
    ("A group of flamingos is called a ___.", "flamboyance"),
    ("The national animal of Scotland is the ___.", "unicorn"),
    ("Wombats are famous for making poop shaped like ___.", "cubes"),
    ("The dot over a lowercase i or j is called a ___.", "tittle"),
    ("The plastic tip on the end of a shoelace is called an ___.", "aglet"),
    ("Before it was called Google, the search engine was called ___.", "BackRub"),
    ("An octopus has ___ hearts.", "three"),
    ("A group of crows is called a ___.", "murder"),
    ("Archaeologists have found honey that's still edible in ancient Egyptian ___.", "tombs"),
    ("The man who designed the Pringles can had some of his ashes buried in a ___.", "Pringles can"),
    ("Bananas are slightly ___.", "radioactive"),
    ("The Eiffel Tower can grow about 6 inches taller in the ___.", "summer"),
    ("Sea otters hold ___ while they sleep so they don't drift apart.", "hands"),
    ("The first product ever scanned with a barcode was a pack of ___.", "gum"),
    ("A shrimp's heart is in its ___.", "head"),
    ("Mr. Potato Head was the first toy ever advertised on ___.", "TV"),
    ("Play-Doh was first sold as a cleaner for ___.", "wallpaper"),
    ("The # symbol's official name is the ___.", "octothorpe"),
    ("A group of owls is called a ___.", "parliament"),
    ("Cap'n Crunch's full name is Horatio Magellan ___.", "Crunch"),
    ("Nintendo started out in 1889 making ___.", "playing cards"),
    ("Before he was famous, Harrison Ford worked as a ___.", "carpenter"),
    ("The national animal of Wales is the ___.", "dragon"),
    ("Koala fingerprints are so much like ___ fingerprints that they could confuse a crime scene.", "human"),
    ("A blue whale's tongue can weigh as much as an ___.", "elephant"),
    ("Peanuts aren't really nuts. They're ___.", "legumes"),
    ("Strawberries aren't technically berries, but ___ are.", "bananas"),
    ("The Twitter bird's official name was ___.", "Larry"),
    ("In the 1830s, ketchup was sold as a ___.", "medicine"),
    ("Abraham Lincoln is in the National ___ Hall of Fame.", "Wrestling"),
    ("The original voice of Mickey Mouse married the voice of ___.", "Minnie Mouse"),
    ("A group of pugs is called a ___.", "grumble"),
    ("The world's first webcam was pointed at a ___.", "coffee pot"),
    ("Cows have best friends and get ___ when they're apart.", "stressed"),
    ("Scotland has more than 400 words for ___.", "snow"),
    ("A group of hippos is called a ___.", "bloat"),
    ("When the man behind the modern Frisbee died, his ashes were made into ___.", "frisbees"),
    ("It's impossible to hum while holding your ___.", "nose"),
    ("The longest English word you can type with only the top row of a keyboard is ___.", "typewriter"),
    ("Hot water can freeze faster than cold water. This is called the ___ effect.", "Mpemba"),
]

TUNE_JUNK = r"\s*[\(\[][^)\]]*(official|video|lyric|audio|hd|4k|remaster|visualizer|music|clip|mv)[^)\]]*[\)\]]"
