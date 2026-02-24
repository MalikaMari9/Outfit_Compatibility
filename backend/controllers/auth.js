import { hash } from "bcryptjs";
import user from "../models/user.js";
import { compare } from "bcryptjs";
import { genToken } from "../utils/jwt.js";

export const register = async (req, res) => {
    try {
        const {name, email, password} = req.body;
        const normalizedRole = "user";
    
        const existing = await  user.findOne({ email });
        if (existing) return res.status(400).json({ message: "Email already in use." });
    
        const hashed = await hash(password, 10);
    
        const newUser = new user({
          name,
          email,
          password: hashed,
          role: normalizedRole
        });
        await newUser.save();
        return res.status(201).json({ message: "User registered successfully.",token: genToken(newUser), role : normalizedRole });
    } catch (err) {
        console.error("Register error:", err);
        return res.status(500).json({ message: "Server error." });
    }
}

export const login = async (req, res) => {
    try {
        
        const { email, password } = req.body;
    
        // Check if user exists
        const existing = await user.findOne({ email });
        if (!existing) {
          return res.status(401).json({ message: "Invalid email or password." });
        }
    
        // Check password
        const isMatch = await compare(password, existing.password);
        if (!isMatch) {
          return res.status(401).json({ message: "Invalid email or password." });
        }
    
        // Generate JWT token
        const token = genToken(existing)
    
        // Respond with success and user info (omit password!)
        const { password: _, ...userData } = existing.toObject(); // remove password
        res.status(200).json({
          message: "Logged in successfully",
          token,
          role : existing.role

        });
    
    } catch (err) {
        console.error("Login error:", err);
        res.status(500).json({ message: "Server error" });
    }
}
