-- =====================================================================
-- Animal Shelter Management System — Database Schema
-- Tables are ordered so every foreign key target already exists
-- by the time it's referenced (parents before children).
-- =====================================================================

CREATE TABLE Animal (
    animal_id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    species VARCHAR(100) NOT NULL,
    breed VARCHAR(50) DEFAULT NULL,
    sex ENUM('Male','Female') NOT NULL,
    birth_date DATE DEFAULT NULL,
    status ENUM('available','pending','adopted','fostered','unavailable') NOT NULL,
    notes TEXT DEFAULT NULL,
    image_url VARCHAR(255) DEFAULT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at DATETIME DEFAULT NULL,
    deleted_by INT DEFAULT NULL,
    PRIMARY KEY (animal_id)
);

CREATE TABLE Vet (
    vet_id INT NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    affiliation VARCHAR(150) DEFAULT NULL,
    PRIMARY KEY (vet_id)
);

CREATE TABLE Vet_Contact (
    contact_id INT NOT NULL AUTO_INCREMENT,
    vet_id INT NOT NULL,
    contact_type ENUM('phone','email') NOT NULL,
    contact_value VARCHAR(150) NOT NULL,
    PRIMARY KEY (contact_id),
    FOREIGN KEY (vet_id) REFERENCES Vet(vet_id)
);

CREATE TABLE Staff (
    staff_id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    role ENUM('admin','staff') NOT NULL,
    status BOOLEAN NOT NULL DEFAULT TRUE,
    password VARCHAR(60) NOT NULL,
    PRIMARY KEY (staff_id)
);

CREATE TABLE Person (
    person_id INT NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (person_id)
);

CREATE TABLE Person_Contact (
    contact_id INT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    contact_type ENUM('phone','email') NOT NULL,
    contact_value VARCHAR(150) NOT NULL,
    PRIMARY KEY (contact_id),
    UNIQUE (contact_value),
    FOREIGN KEY (person_id) REFERENCES Person(person_id)
);

CREATE TABLE Medical_Record (
    record_id INT NOT NULL AUTO_INCREMENT,
    animal_id INT NOT NULL,
    visit_date DATE NOT NULL,
    outcome VARCHAR(100) DEFAULT NULL,
    PRIMARY KEY (record_id),
    FOREIGN KEY (animal_id) REFERENCES Animal(animal_id)
);

CREATE TABLE Treatment (
    treatment_id INT NOT NULL AUTO_INCREMENT,
    record_id INT NOT NULL,
    vet_id INT NOT NULL,
    treatment_type VARCHAR(100) NOT NULL,
    medication VARCHAR(100) DEFAULT NULL,
    description TEXT DEFAULT NULL,
    cost DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (treatment_id),
    FOREIGN KEY (record_id) REFERENCES Medical_Record(record_id),
    FOREIGN KEY (vet_id) REFERENCES Vet(vet_id)
);

CREATE TABLE Edit_Request (
    record_id INT NOT NULL AUTO_INCREMENT,
    request_id INT DEFAULT NULL,
    table_name VARCHAR(50) NOT NULL,
    record_type ENUM('create','update') NOT NULL,
    field_changes TEXT NOT NULL,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME DEFAULT NULL,
    reviewed_by INT DEFAULT NULL,
    PRIMARY KEY (record_id),
    FOREIGN KEY (reviewed_by) REFERENCES Staff(staff_id)
);

CREATE TABLE Rescue (
    rescue_id INT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    animal_id INT DEFAULT NULL,
    rescue_date DATE NOT NULL,
    location VARCHAR(150) DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    animal_species VARCHAR(100) NOT NULL,
    animal_name_snapshot VARCHAR(50) DEFAULT NULL,
    photo_url VARCHAR(255) DEFAULT NULL,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INT DEFAULT NULL,
    PRIMARY KEY (rescue_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id),
    FOREIGN KEY (animal_id) REFERENCES Animal(animal_id),
    FOREIGN KEY (reviewed_by) REFERENCES Staff(staff_id)
);

CREATE TABLE Adoption (
    adoption_id INT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    animal_id INT NOT NULL,
    adoption_date DATE DEFAULT NULL,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INT DEFAULT NULL,
    PRIMARY KEY (adoption_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id),
    FOREIGN KEY (animal_id) REFERENCES Animal(animal_id),
    FOREIGN KEY (reviewed_by) REFERENCES Staff(staff_id)
);

CREATE TABLE Foster (
    foster_id INT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    animal_id INT NOT NULL,
    start_date DATE DEFAULT NULL,
    end_date DATE DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INT DEFAULT NULL,
    PRIMARY KEY (foster_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id),
    FOREIGN KEY (animal_id) REFERENCES Animal(animal_id),
    FOREIGN KEY (reviewed_by) REFERENCES Staff(staff_id)
);

CREATE TABLE Donation_Info (
    info_id INT NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) NOT NULL,
    content VARCHAR(255) NOT NULL,
    is_image BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by INT NOT NULL,
    PRIMARY KEY (info_id),
    FOREIGN KEY (updated_by) REFERENCES Staff(staff_id)
);
