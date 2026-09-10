import arcArtwork from "@assets/arc-artwork.jpeg";

/** The ARC signal mark — the real artwork, with the brand gradient wash. */
export default function BrandMark({ small = false }: { small?: boolean }) {
  return (
    <div className={`relative overflow-hidden rounded-xl ${small ? "h-8 w-8" : "h-11 w-11"}`}>
      <img src={arcArtwork} alt="ARC signal mark" className="h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-tr from-cyan-400/20 via-transparent to-fuchsia-500/30" />
    </div>
  );
}
