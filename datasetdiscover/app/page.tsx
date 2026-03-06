import { Navbar } from "./components/Navbar";
import { Hero } from "./components/Hero";
import { Features } from "./components/Features";
import { ToolsSection } from "./components/ToolsSection";
import { StepsSection } from "./components/StepsSection";
import { Footer } from "./components/Footer";

export default function Home() {
  return (
    <div className="bg-white dark:bg-black min-h-screen">
      <Navbar />
      <Hero />
      <Features />
      <ToolsSection />
      <StepsSection />
      <Footer />
    </div>
  );
}
