import mongoose, { Schema } from "mongoose";

const clothingSchema = new Schema({
    imagePath : {type : String, required : true},
    userId : {type : Schema.ObjectId, ref : "user", required : true},
    details : {type : Object, required : true},
    createdAt : {type : Date, default : Date.now}
})

const clothing = mongoose.model('clothing', clothingSchema);
export default clothing;
