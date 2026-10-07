"""Invented review texts for the synthetic demo worlds.

Each AI-styled text comes with the phrases an AI-text opinion would quote for it; the demo fixtures store those as
the opinion (labelled synthetic), because demo mode never calls a model. Every text here is invented.
"""

from __future__ import annotations

# (text, quoted cues) written in the polished style chatbots produce.
MOVERS_AI: list[tuple[str, list[str]]] = [
    (
        "I recently used their packing and moving services for my relocation, and I must say the experience was "
        "absolutely seamless. From the initial survey to the final delivery, the team demonstrated impeccable "
        "professionalism and attention to detail. Every item was packed with care and arrived in perfect condition. "
        "Overall, I can't recommend them enough for anyone looking for a stress-free move!",
        ["the experience was absolutely seamless", "impeccable professionalism and attention to detail"],
    ),
    (
        "Moving homes can be overwhelming, but this team made the entire process effortless. Their staff were "
        "punctual, courteous, and incredibly efficient. They handled our furniture and fragile items with the utmost "
        "care, ensuring nothing was damaged. The pricing was transparent with no hidden charges. Whether you're moving "
        "across the city or across the country, this is the team to trust. Highly recommended!",
        ["made the entire process effortless", "Whether you're moving across the city or across the country"],
    ),
    (
        "Exceptional service from start to finish! The team was professional, punctual, and handled all our "
        "belongings with great care. Communication was clear throughout, and they kept us informed at every step. "
        "The packing materials were of top-notch quality. Truly a hassle-free experience that exceeded my "
        "expectations. Five stars without a doubt!",
        ["Exceptional service from start to finish", "Truly a hassle-free experience that exceeded my expectations"],
    ),
    (
        "Pros: Punctual team, careful packing, transparent pricing, smooth unloading. Cons: None that I can think of. "
        "Overall, a truly outstanding relocation experience. The crew went above and beyond to ensure every item "
        "reached safely, and their customer support was responsive and helpful throughout the journey. A testament "
        "to their commitment to quality.",
        ["Cons: None that I can think of", "A testament to their commitment to quality"],
    ),
    (
        "I was nervous about shifting my entire household, but this company turned what could have been a stressful "
        "ordeal into a smooth and seamless experience. The team arrived on time, wrapped everything meticulously, and "
        "unpacked with remarkable efficiency. Their dedication to customer satisfaction is evident in every step. In "
        "conclusion, an excellent choice for anyone relocating.",
        ["a smooth and seamless experience", "Their dedication to customer satisfaction is evident in every step"],
    ),
    (
        "From the moment I contacted them, I knew I was in good hands. The representative patiently answered all my "
        "questions and provided a detailed quotation. On moving day, the crew worked like a well-oiled machine, "
        "packing, loading, and transporting everything with precision. Not a single scratch on my furniture! Truly a "
        "five-star service that I would wholeheartedly recommend.",
        ["the crew worked like a well-oiled machine", "a five-star service that I would wholeheartedly recommend"],
    ),
]

# A real customer's specific review, polished with AI: the opinion still says "AI-written". Kept by default.
MOVERS_POLISHED = (
    "Used them for a 2BHK shift across the city in August. Overall, the experience was smooth and well-coordinated. "
    "The team was punctual and handled our belongings with care, although the unloading took slightly longer than "
    "expected. Communication was prompt and professional throughout. A reliable option for intra-city moves, and I'd "
    "consider them again.",
    ["Overall, the experience was smooth and well-coordinated", "Communication was prompt and professional throughout"],
)

# Long, specific texts a person typed: the opinion reads them as human. (text, rating)
MOVERS_HUMAN: list[tuple[str, int]] = [
    (
        "Booked them for shifting to the other side of the city. Rajesh bhaiya and team came at 9am sharp, packing "
        "was good but they charged 1500 extra for the fridge which was not told before. One chair leg broke, they "
        "gave 500 rs adjustment after I complained. Overall ok, giving 3 star.",
        3,
    ),
    (
        "Very bad experience. They told 2 days delivery for Pune but took 9 days, every day calling them they say "
        "tomorrow tomorrow. Finally came and my TV box was damaged, still fighting for claim. Dont go by the 5 star "
        "reviews here, check the 1 star ones also before booking.",
        1,
    ),
    (
        "Shifted my parents house within the same area. Team of 4 people came, they were careful with my mother's "
        "glass showpieces and old wooden almirah. Price was 9500 which was ok compared to other quotes we got. Only "
        "thing is supervisor was on phone whole time, but work got done in 5 hours.",
        4,
    ),
    (
        "bhai log ne ekdum mast kaam kiya, saman sab safe pahuch gaya. bike bhi bheji thi Hyderabad, 6 din me aa gayi "
        "bina scratch ke. rate thoda zyada laga but chalta hai, service acchi thi. Ramesh ji ka number save karke "
        "rakho next time ke liye, bahut helpful hai.",
        5,
    ),
    (
        "Third time using them, earlier also for office shifting. This time they sent new boys who didnt know how to "
        "dismantle the bed properly, took 2 hours extra. Called the owner and he sent senior person who fixed it. "
        "Good that they take responsibility but training is needed for the new staff.",
        3,
    ),
    (
        "Was a little skeptical after reading mixed reviews but the experience was decent. They gave written "
        "quotation of Rs 18,000 for 2BHK to Chennai with insurance. Truck came one day late due to some issue at the "
        "state border, they informed in advance though. All items reached fine except a small dent on the washing "
        "machine.",
        4,
    ),
]

# Short, generic texts posted by the burst of first-time accounts.
MOVERS_BURST_SHORT = [
    "Excellent service",
    "Very good packers and movers",
    "Best movers in town",
    "Good work, highly recommended",
    "Superb service by the team",
    "Nice and professional",
    "Very good experience",
    "Excellent team, on time",
    "Five star service",
    "Good",
    "Very nice service",
    "Best service",
    "",
    "",
]
# One template several burst accounts paste, with small edits: copied text.
MOVERS_TEMPLATE = "Very professional team, packed everything carefully and delivered on time. Highly recommended!"

MOVERS_CHATBOT = (
    "Sure! Here's a review you can post: The team at [Business Name] made our move completely stress-free. They "
    "were punctual, careful and friendly."
)

HOTEL_AI: list[tuple[str, list[str]]] = [
    (
        "Nestled in the heart of the city, this hotel offers a perfect blend of comfort and convenience. The rooms "
        "were spacious, impeccably clean, and thoughtfully designed. The staff went above and beyond to make our stay "
        "memorable. Whether you're traveling for work or leisure, this hotel is a hidden gem that truly delivers. "
        "Highly recommended!",
        ["Nestled in the heart of the city", "a hidden gem that truly delivers"],
    ),
    (
        "Our stay was nothing short of exceptional. From the warm welcome at the reception to the delightful "
        "breakfast spread, every detail was taken care of. The rooms were cozy and well-maintained, offering a "
        "peaceful retreat after a long day of sightseeing. Overall, an unforgettable experience that I would "
        "recommend to anyone visiting the capital.",
        ["Our stay was nothing short of exceptional", "offering a peaceful retreat after a long day of sightseeing"],
    ),
    (
        "Exceptional hospitality and top-notch service! The staff were incredibly attentive and ensured that our every "
        "need was met. The location is perfect for exploring the vibrant markets and historic landmarks nearby. A "
        "truly delightful stay that exceeded all my expectations. I can't wait to return on my next visit!",
        ["Exceptional hospitality and top-notch service", "A truly delightful stay that exceeded all my expectations"],
    ),
]

HOTEL_HUMAN: list[tuple[str, int]] = [
    (
        "Room was not like photos at all. AC was making noise whole night and bathroom tap was leaking. Asked for room "
        "change at 11pm, they said no rooms available. Breakfast was only bread butter and tea. For 2200 per night not "
        "worth it, location is good near station that's the only plus.",
        2,
    ),
    (
        "Stayed 2 nights with family. Staff was helpful, Mr. Arjun at reception arranged early check in at 8am for us "
        "without extra charge. Rooms are small but clean, bedsheets were fresh. Lift was not working one day, we were "
        "on 4th floor so it was difficult with luggage and my father's knee problem.",
        4,
    ),
    (
        "Booked through an app, at check in they said booking not received and asked to pay again in cash. After 45 "
        "min of arguing they gave a room. Hot water came only after 10 minutes of running. Dont book here if you have "
        "kids, the lane outside is very noisy till 2am.",
        1,
    ),
    (
        "Budget hotel, you get what you pay for. Room was basic and wifi was weak on the third floor, but bed was "
        "comfortable and the night staff helped us book a cab to the airport at 4am. Would stay again for one night "
        "transit, not for a longer holiday with family.",
        3,
    ),
]

HOTEL_CHATBOT = (
    "I'm unable to generate a review for you, but I can help you outline key points: cleanliness, staff behaviour, "
    "location, value for money."
)

HOTEL_OLD_BATCH = [
    "Excellent hotel",
    "Very good stay",
    "Best hotel near station",
    "Nice rooms and staff",
    "Good hotel, value for money",
    "Superb",
    "Very nice",
    "Awesome stay",
    "",
]
