"""Curated collection of romantic and love quotes for the magazine."""

ROMANTIC_QUOTES = [
    # Timeless classics
    {
        "text": "I have found the one whom my soul loves.",
        "author": "Song of Solomon 3:4",
    },
    {
        "text": "Whatever our souls are made of, his and mine are the same.",
        "author": "Emily Bront\u00eb",
    },
    {
        "text": "In all the world, there is no heart for me like yours. In all the world, there is no love for you like mine.",
        "author": "Maya Angelou",
    },
    {
        "text": "I would rather spend one lifetime with you, than face all the ages of this world alone.",
        "author": "J.R.R. Tolkien",
    },
    {
        "text": "You are my today and all of my tomorrows.",
        "author": "Leo Christopher",
    },
    {
        "text": "Grow old along with me! The best is yet to be.",
        "author": "Robert Browning",
    },
    {
        "text": "The best thing to hold onto in life is each other.",
        "author": "Audrey Hepburn",
    },
    {
        "text": "Love recognizes no barriers. It jumps hurdles, leaps fences, penetrates walls to arrive at its destination full of hope.",
        "author": "Maya Angelou",
    },
    {
        "text": "To love and be loved is to feel the sun from both sides.",
        "author": "David Viscott",
    },
    {
        "text": "I love you not because of who you are, but because of who I am when I am with you.",
        "author": "Roy Croft",
    },
    # Poetic & lyrical
    {
        "text": "If I had a flower for every time I thought of you, I could walk through my garden forever.",
        "author": "Alfred Tennyson",
    },
    {
        "text": "You don\u2019t love someone for their looks, or their clothes, or for their fancy car, but because they sing a song only you can hear.",
        "author": "Oscar Wilde",
    },
    {
        "text": "I carry your heart with me. I carry it in my heart.",
        "author": "E.E. Cummings",
    },
    {
        "text": "Come live in my heart and pay no rent.",
        "author": "Samuel Lover",
    },
    {
        "text": "Two souls with but a single thought, two hearts that beat as one.",
        "author": "Friedrich Halm",
    },
    {
        "text": "Love is composed of a single soul inhabiting two bodies.",
        "author": "Aristotle",
    },
    # Warm & intimate
    {
        "text": "I saw that you were perfect, and so I loved you. Then I saw that you were not perfect and I loved you even more.",
        "author": "Angelita Lim",
    },
    {
        "text": "Being deeply loved by someone gives you strength, while loving someone deeply gives you courage.",
        "author": "Lao Tzu",
    },
    {
        "text": "The greatest thing you\u2019ll ever learn is just to love and be loved in return.",
        "author": "Eden Ahbez",
    },
    {
        "text": "You are the finest, loveliest, tenderest, and most beautiful person I have ever known \u2014 and even that is an understatement.",
        "author": "F. Scott Fitzgerald",
    },
    {
        "text": "When I look into your eyes, I know I have found the mirror of my soul.",
        "author": "Joey W. Hill",
    },
    {
        "text": "Every love story is beautiful, but ours is my favorite.",
        "author": "Anonymous",
    },
    {
        "text": "I love you more than I have ever found a way to say to you.",
        "author": "Ben Folds",
    },
    {
        "text": "You are my heart, my life, my one and only thought.",
        "author": "Arthur Conan Doyle",
    },
    # Journey & togetherness
    {
        "text": "Life is a journey, and love is what makes that journey worthwhile.",
        "author": "Anonymous",
    },
    {
        "text": "Side by side or miles apart, we are connected by the heart.",
        "author": "Anonymous",
    },
    {
        "text": "In you, I\u2019ve found the love of my life and my closest, truest friend.",
        "author": "Anonymous",
    },
    {
        "text": "Loved you yesterday, love you still. Always have, always will.",
        "author": "Elaine Davis",
    },
    {
        "text": "You are my sun, my moon, and all my stars.",
        "author": "E.E. Cummings",
    },
    {
        "text": "I never want to stop making memories with you.",
        "author": "Pierre Jeanty",
    },
    {
        "text": "Home is wherever I\u2019m with you.",
        "author": "Edward Sharpe",
    },
    {
        "text": "You are every reason, every hope, and every dream I\u2019ve ever had.",
        "author": "Nicholas Sparks",
    },
    {
        "text": "A hundred hearts would be too few to carry all my love for you.",
        "author": "Henry Wadsworth Longfellow",
    },
    {
        "text": "Love is not about how many days, months, or years you have been together. Love is about how much you love each other every single day.",
        "author": "Anonymous",
    },
]


def get_quotes(count: int = 6) -> list[dict]:
    """Return a selection of quotes for the magazine.

    Picks evenly spaced quotes from the collection to ensure variety.
    """
    total = len(ROMANTIC_QUOTES)
    if count >= total:
        return ROMANTIC_QUOTES[:]

    step = total / count
    indices = [int(i * step) for i in range(count)]
    return [ROMANTIC_QUOTES[i] for i in indices]
