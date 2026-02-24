import jwt from "jsonwebtoken";
import { JWT_SECRET, JWT_EXPIRES_IN } from "../config.js";

const {sign, verify} = jwt;

export const genToken = ({_id, role}) => {
    return sign(
      { id: _id, role :  role},
      JWT_SECRET,
      { expiresIn: JWT_EXPIRES_IN || "1d" }
    );
}

export const verifyToken = async (authHeader) => {
    if (!authHeader || !authHeader.startsWith("Bearer "))
        return null;
    const token = authHeader.split(" ")[1];
    try{
        const decoded = verify(token, JWT_SECRET);
        return decoded;
    }catch(err){
        console.error(err);
        return null;
    }
  };

