import mongoose, { Schema } from "mongoose";

const feedbackReportSchema = new Schema(
  {
    userId: { type: Schema.ObjectId, ref: "user", default: null },
    page: { type: String, required: true, trim: true, lowercase: true },
    message: { type: String, required: true, trim: true },
    status: {
      type: String,
      enum: ["pending", "resolved", "dismissed"],
      default: "pending",
    },
    details: { type: Object, default: {} },
  },
  {
    timestamps: true,
  },
);

const feedbackReport = mongoose.model("feedback_report", feedbackReportSchema);
export default feedbackReport;
