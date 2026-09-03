-- SplitBites PostgreSQL Schema (with pgvector)
-- Rev 1.2 Alignment

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- User Profile & Household Management
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS households (
    household_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS household_members (
    household_id UUID REFERENCES households(household_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',
    PRIMARY KEY (household_id, user_id)
);

CREATE TABLE IF NOT EXISTS dietary_preferences (
    preference_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    preference_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS household_dietary_restrictions (
    household_id UUID REFERENCES households(household_id) ON DELETE CASCADE,
    preference_id UUID REFERENCES dietary_preferences(preference_id) ON DELETE CASCADE,
    PRIMARY KEY (household_id, preference_id)
);

-- Recipes & Catalog (with pgvector embedding)
CREATE TABLE IF NOT EXISTS recipes (
    recipe_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    creator_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    prep_time_minutes INT,
    difficulty_level VARCHAR(50),
    instructions JSONB NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding vector(1536)
);

-- Ensure embedding column exists if table was pre-existing
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE TABLE IF NOT EXISTS recipe_dietary_tags (
    recipe_id UUID REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    preference_id UUID REFERENCES dietary_preferences(preference_id) ON DELETE CASCADE,
    PRIMARY KEY (recipe_id, preference_id)
);

CREATE TABLE IF NOT EXISTS ingredients (
    ingredient_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingredient_name VARCHAR(255) UNIQUE NOT NULL,
    default_unit VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id UUID REFERENCES recipes(recipe_id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    quantity DECIMAL(10, 2) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    PRIMARY KEY (recipe_id, ingredient_id)
);

-- Meal Planning & Schedules
CREATE TABLE IF NOT EXISTS meal_plans (
    plan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID REFERENCES households(household_id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meal_plan_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meal_plan_id UUID REFERENCES meal_plans(plan_id) ON DELETE CASCADE,
    recipe_id UUID REFERENCES recipes(recipe_id) ON DELETE SET NULL,
    day_of_week VARCHAR(20) NOT NULL,
    is_modified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Aliases / legacy compatibility tables
CREATE TABLE IF NOT EXISTS weekly_meal_plans (
    plan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID REFERENCES households(household_id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_slots (
    slot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id UUID REFERENCES weekly_meal_plans(plan_id) ON DELETE CASCADE,
    day_of_week VARCHAR(20) NOT NULL,
    recipe_id UUID REFERENCES recipes(recipe_id) ON DELETE SET NULL,
    is_swapped BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS retailer_pricing (
    pricing_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingredient_id UUID REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    retailer_name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    package_size VARCHAR(100),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
