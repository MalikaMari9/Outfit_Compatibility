import mongoose, {Schema} from "mongoose";

const userSchema = new Schema({
    name : {type : String, required : true},
    email : {type : String, required : true},
    password : {type : String, required : true},
    bio : {type : String},
    role : {type : String, required : true},
    createdAt : {type : Date, default : Date.now}
})

const user = mongoose.model('user', userSchema);
export default user;
