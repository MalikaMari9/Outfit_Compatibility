import user from "../models/user.js";
import { verifyToken } from "../utils/jwt.js"

export const getUserData = async (req, res) => {
    try{
        const authHeader = req.headers.authorization;
        
        if(!authHeader){
            return res.status(401).json({message : "Unauthorized access"});
        }
        console.log(authHeader);
        
        const decoded = await verifyToken(authHeader);
        if (!decoded) {
            return res.status(401).json({message : "Unauthorized access"});
        }
        const {id} = decoded;    
        const accountData = await user.findById(id).select("-password");
        if(!accountData){
            return res.status(404).json({message : "User not found"})
        }
        return res.status(200).json({message : "Fetched successfully", user : accountData})
    }catch(err){
        console.error(err);
        return res.status(500).json({message : "Server error"});
    }
}

export const updateUserData = async (req, res) => {
    try {
        const authHeader = req.headers.authorization;

        if(!authHeader){
            return res.status(401).json({message : "Unauthorized access"});
        }
        console.log(authHeader);

        const decoded = await verifyToken(authHeader);
        if (!decoded) {
            return res.status(401).json({message : "Unauthorized access"});
        }
        const {id} = decoded;
        const updateData = req.body;
        const accountData = await user.findByIdAndUpdate(id, updateData, {new : true});
        
        if (!accountData) {
            return res.status(404).json({message : "User not found"});
        } else {
            return res.status(201).json({message : "Updated successfully", user : accountData})
        }
        
    } catch (err) {
        console.error(err);
        return res.status(500).json({message : "Server error"});
        
    }
}


export const recommendOutfit = async (req, res) => {
    try{
        const authHeader = req.headers.authorization;
        
        if(!authHeader)
            return res.status(401).json({message : "Unauthorized access"});
        const decoded = await verifyToken(authHeader);
        if (!decoded) {
            return res.status(401).json({message : "Unauthorized access"});
        }
        const {id} = decoded;

        if (!req.file) {
            return res.status(400).send('No file uploaded');
        }

        
        res.status(201).json({
            message: 'File uploaded successfully!',
            filePath: req.file.path
        });

    }catch(err){
        console.log(err);
        return res.status(500).json({message : "Server error"});
        
    }
}

export const compatibilityCheck = async (req, res) => {
    try{
        const authHeader = req.headers.authorization;
        if(!authHeader)
            return res.status(401).json({message : "Unauthorized access"});
        const decoded = await verifyToken(authHeader);
        if (!decoded) {
            return res.status(401).json({message : "Unauthorized access"});
        }
        const {id} = decoded;

        if(!req.files)
            return res.status(400).json({message : "No file uploaded"});

    }catch(err){
        console.log(err);
        return res.status(500).json({message : "Server error"});
    }
}
